function check_time()
    local current_time = mp.get_property_number("time-pos")
    local total_time = mp.get_property_number("duration")
    
    if current_time and total_time then
        if total_time - current_time <= 1 then
            mp.command("quit")
        end
    end
end

mp.add_periodic_timer(1, check_time)