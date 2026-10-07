-- Exit with status 0 when a double tap is seen on the given touchscreen device.
-- Usage: luajit doubletap.lua /dev/input/eventN
-- Runs under KOReader's LuaJIT. Reads raw evdev events (32-bit timeval on the Kindle).
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
local ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID = 0x35, 0x36, 0x39

local MAX_TAP = 0.35     -- a tap is a touch shorter than this (s)
local MAX_GAP = 0.50     -- second tap must start within this of the first tap's start (s)
local MAX_MOVE = 120     -- taps must be within this distance of each other (touch units)

local dev = assert(arg[1], "usage: doubletap.lua /dev/input/eventN")
local f = assert(io.open(dev, "rb"))
local ev = ffi.new("struct dash_input_event")

local touching, down_t, x, y, down_x, down_y = false, 0, 0, 0, nil, nil
local last_tap = nil   -- {t, x, y} of the previous completed tap

local function down(t)
    if touching then return end
    touching, down_t = true, t
    down_x, down_y = nil, nil   -- filled in by the first position reports of this touch
end

local function up(t)
    if not touching then return end
    touching = false
    down_x, down_y = down_x or x, down_y or y
    if t - down_t > MAX_TAP then last_tap = nil; return end
    if last_tap and down_t - last_tap.t <= MAX_GAP
            and math.abs(down_x - last_tap.x) <= MAX_MOVE and math.abs(down_y - last_tap.y) <= MAX_MOVE then
        io.stdout:write(string.format("double tap at %d,%d\n", down_x, down_y))
        os.exit(0)
    end
    last_tap = { t = down_t, x = down_x, y = down_y }
end

while true do
    local buf = f:read(EV_SIZE)
    if not buf or #buf < EV_SIZE then os.exit(1) end
    ffi.copy(ev, buf, EV_SIZE)
    local t = ev.sec + ev.usec / 1e6
    if ev.type == EV_ABS then
        if ev.code == ABS_MT_POSITION_X or ev.code == ABS_X then
            x = ev.value
            if touching and not down_x then down_x = x end
        elseif ev.code == ABS_MT_POSITION_Y or ev.code == ABS_Y then
            y = ev.value
            if touching and not down_y then down_y = y end
        elseif ev.code == ABS_MT_TRACKING_ID then
            if ev.value >= 0 then down(t) else up(t) end
        end
    elseif ev.type == EV_KEY and ev.code == BTN_TOUCH then
        if ev.value == 1 then down(t) else up(t) end
    end
end
