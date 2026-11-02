-- Touch gesture detector for the dashboard. Prints one line per gesture and keeps running:
--   double-tap X,Y      two quick taps close together (dash.sh exits to the Kindle UI)
--   swipe-left          one quick horizontal stroke towards the left edge (next page)
--   swipe-right         ... towards the right edge (previous page)
-- Usage: luajit gestures.lua /dev/input/eventN
-- Runs under KOReader's LuaJIT. Reads raw evdev events (32-bit timeval on the Kindle) and
-- exits only when the device reports EOF or an error.
local ffi = require("ffi")
ffi.cdef[[
struct dash_input_event {
    int32_t sec; int32_t usec;
    uint16_t type; uint16_t code; int32_t value;
};
]]

local EV_SIZE = ffi.sizeof("struct dash_input_event")   -- 16
local EV_KEY, EV_ABS = 1, 3
local BTN_TOUCH = 0x14a
local ABS_X, ABS_Y = 0x00, 0x01
local ABS_MT_SLOT = 0x2f
local ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x35, 0x36, 0x39

local MAX_TAP = 0.35     -- a tap is a touch shorter than this (s) ...
local MAX_MOVE = 120     -- ... that stays within this distance of where it started (touch units);
                         -- the two taps of a double tap must also be within this of each other
local MAX_GAP = 0.50     -- second tap must start within this of the first tap's start (s)
local SWIPE_MIN = 250    -- a swipe moves at least this far horizontally (touch units) ...
local SWIPE_TIME = 1.0   -- ... within this long (s), and more than twice as far across as up/down

local dev = assert(arg[1], "usage: gestures.lua /dev/input/eventN")
local f = assert(io.open(dev, "rb"))
local ev = ffi.new("struct dash_input_event")
io.stdout:setvbuf("line")

local function emit(s)
    io.stdout:write(s, "\n")
    io.stdout:flush()
end

local slot = 0                 -- multitouch slot the following ABS_MT_* events belong to
local touching = false
local touch_slot = 0           -- slot of the finger that started the current touch
local multi = false            -- a second finger joined: the touch is neither a tap nor a swipe
local down_t, x, y, down_x, down_y = 0, 0, 0, nil, nil
local last_tap = nil           -- {t, x, y} of the previous completed tap

local function down(t)
    if touching then return end
    touching, down_t, touch_slot, multi = true, t, slot, false
    down_x, down_y = nil, nil   -- filled in by the first position reports of this touch
end

local function up(t)
    if not touching then return end
    touching = false
    down_x, down_y = down_x or x, down_y or y
    local dur, dx, dy = t - down_t, x - down_x, y - down_y
    if multi then last_tap = nil; return end
    if math.abs(dx) >= SWIPE_MIN and math.abs(dx) > 2 * math.abs(dy) and dur <= SWIPE_TIME then
        last_tap = nil          -- a swipe is never a tap, and never pairs with the tap before it
        emit(dx < 0 and "swipe-left" or "swipe-right")
        return
    end
    if dur > MAX_TAP or math.abs(dx) > MAX_MOVE or math.abs(dy) > MAX_MOVE then
        last_tap = nil          -- a press or a drag: not a tap
        return
    end
    if last_tap and down_t - last_tap.t <= MAX_GAP
            and math.abs(down_x - last_tap.x) <= MAX_MOVE and math.abs(down_y - last_tap.y) <= MAX_MOVE then
        last_tap = nil
        emit(string.format("double-tap %d,%d", down_x, down_y))
        return
    end
    last_tap = { t = down_t, x = down_x, y = down_y }
end

local function position(is_x, v)
    if touching and slot ~= touch_slot then return end   -- another finger
    if is_x then
        x = v
        if touching and not down_x then down_x = v end
    else
        y = v
        if touching and not down_y then down_y = v end
    end
end

while true do
    local buf = f:read(EV_SIZE)
    if not buf or #buf < EV_SIZE then
        io.stderr:write("gestures.lua: ", dev, " closed\n")
        os.exit(1)
    end
    ffi.copy(ev, buf, EV_SIZE)
    local t = ev.sec + ev.usec / 1e6
    if ev.type == EV_ABS then
        if ev.code == ABS_MT_SLOT then
            slot = ev.value
        elseif ev.code == ABS_MT_POSITION_X or ev.code == ABS_X then
            position(true, ev.value)
        elseif ev.code == ABS_MT_POSITION_Y or ev.code == ABS_Y then
            position(false, ev.value)
        elseif ev.code == ABS_MT_TRACKING_ID then
            if ev.value >= 0 then
                if touching and slot ~= touch_slot then multi = true else down(t) end
            elseif slot == touch_slot then
                up(t)
            end
        end
    elseif ev.type == EV_KEY and ev.code == BTN_TOUCH then
        if ev.value == 1 then down(t) else up(t) end
    end
end
