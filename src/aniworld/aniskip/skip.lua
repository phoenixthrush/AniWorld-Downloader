local mpv = require('mp')
local mpv_options = require("mp.options")

local options = {
    op_start = 0, op_end = 0, ed_start = 0, ed_end = 0,
}
mpv_options.read_options(options, "skip")

local function skip()
    local current_time = mp.get_property_number("time-pos")

    if not current_time then
        return
    end

    if current_time >= options.op_start and current_time < options.op_end then
        mp.set_property_number("time-pos", options.op_end)
    end

    if current_time >= options.ed_start and current_time < options.ed_end then
        mp.set_property_number("time-pos", options.ed_end)
    end
end

mp.observe_property("time-pos", "number", skip)