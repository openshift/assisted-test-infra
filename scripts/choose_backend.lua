core.Debug("Loading lua code for routing to the right backend")

local function find_backend(txn)
    local sni = txn.f:req_ssl_sni()
    core.Debug("Routing sni " .. sni)

    for _, backend in pairs(core.backends) do
        for _, server in pairs(backend.servers) do
	        if server:get_stats()["svname"] == sni then
                core.Debug("Backend " .. backend.name .. " matches")
	            return backend.name
            end
        end
    end
    core.Warning("No backend matched!")
    return nil
end

core.register_fetches('choose_backend', find_backend)
