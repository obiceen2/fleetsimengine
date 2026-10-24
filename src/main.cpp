#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <nlohmann/json.hpp>

#include "SimulationEngine.hpp"

using json = nlohmann::json;

json cargoToJson(const std::vector<CargoLot>& cargo) {
    json result = json::array();

    for (const CargoLot& lot : cargo) {
        result.push_back({
            {"destination", lot.destination},
            {"quantity", lot.quantity}
        });
    }

    return result;
}

json dockCargoToJson(const std::vector<DockCargoLot>& cargo) {
    json result = json::array();

    for (const DockCargoLot& lot : cargo) {
        result.push_back({
            {"location", lot.location},
            {"destination", lot.destination},
            {"quantity", lot.quantity}
        });
    }

    return result;
}

json vesselToJson(const VesselState& vessel) {
    json cargo = cargoToJson(vessel.cargo);

    if (vessel.status == VesselStatus::Idle) {
        return {
            {"state", "idle"},
            {"location", vessel.location},
            {"cargo", std::move(cargo)}
        };
    }

    if (vessel.status == VesselStatus::Transit) {
        return {
            {"state", "transit"},
            {"from", vessel.from},
            {"to", vessel.to},
            {"arrives_at_tick", vessel.arrivesAtTick},
            {"cargo", std::move(cargo)}
        };
    }

    if (vessel.status == VesselStatus::Docked) {
        return {
            {"state", "docked"},
            {"location", vessel.location},
            {"cargo", std::move(cargo)}
        };
    }

    throw std::runtime_error("invalid vessel status");
}

json worldToJson(const WorldState& world) {
    json vessels = json::object();

    for (const auto& [id, vessel] : world.vessels) {
        vessels[id] = vesselToJson(vessel);
    }

    return {
        {"tick", world.tick},
        {"vessels", std::move(vessels)},
        {"cargo", dockCargoToJson(world.cargo)}
    };
}

void writeJson(const json& response) {
    std::cout << response.dump() << '\n' << std::flush;
}

void writeError(const std::string& message) {
    writeJson({
        {"status", "error"},
        {"payload", {{"message", message}}}
    });
}

int readInt(const json& value) {
    if (!value.is_number_integer()) {
        throw std::runtime_error("expected integer");
    }

    if (value.is_number_unsigned()) {
        const uint64_t number = value.get<uint64_t>();

        if (number > static_cast<uint64_t>(std::numeric_limits<int>::max())) {
            throw std::runtime_error("integer out of range");
        }

        return static_cast<int>(number);
    }

    const int64_t number = value.get<int64_t>();

    if (number < std::numeric_limits<int>::min() ||
        number > std::numeric_limits<int>::max()) {
        throw std::runtime_error("integer out of range");
    }

    return static_cast<int>(number);
}

int readIntField(const json& object, const char* key) {
    if (!object.contains(key)) {
        throw std::runtime_error(std::string("missing ") + key);
    }

    return readInt(object.at(key));
}

std::string readStringField(const json& object, const char* key) {
    if (!object.contains(key)) {
        throw std::runtime_error(std::string("missing ") + key);
    }

    if (!object.at(key).is_string()) {
        throw std::runtime_error(std::string(key) + " must be a string");
    }

    return object.at(key).get<std::string>();
}

std::vector<ManifestEntry> readManifest(const json& parameters) {
    if (!parameters.contains("cargo_manifest")) {
        return {};
    }

    const json& manifest = parameters.at("cargo_manifest");

    if (!manifest.is_array()) {
        throw std::runtime_error("cargo_manifest must be an array");
    }

    std::vector<ManifestEntry> entries;
    entries.reserve(manifest.size());

    for (const json& item : manifest) {
        if (!item.is_object()) {
            throw std::runtime_error("cargo manifest entry must be an object");
        }

        ManifestEntry entry;
        entry.location = readIntField(item, "location");
        entry.destination = readIntField(item, "destination");
        entry.quantity = readIntField(item, "quantity");
        entries.push_back(entry);
    }

    return entries;
}

void initializeFromJson(SimulationEngine& engine, const json& parameters) {
    if (!parameters.contains("travel_times")) {
        throw std::runtime_error("missing travel_times");
    }

    if (!parameters.contains("dock_throughput")) {
        throw std::runtime_error("missing dock_throughput");
    }

    if (!parameters.contains("vessels")) {
        throw std::runtime_error("missing vessels");
    }

    const json& matrix = parameters.at("travel_times");
    const json& throughputJson = parameters.at("dock_throughput");
    const json& inputVessels = parameters.at("vessels");

    if (!matrix.is_array()) {
        throw std::runtime_error("travel_times must be an array");
    }

    if (!throughputJson.is_array()) {
        throw std::runtime_error("dock_throughput must be an array");
    }

    if (!inputVessels.is_array()) {
        throw std::runtime_error("vessels must be an array");
    }

    std::vector<std::vector<int>> times;
    times.reserve(matrix.size());

    for (const json& row : matrix) {
        if (!row.is_array()) {
            throw std::runtime_error("each travel time row must be an array");
        }

        std::vector<int> parsedRow;
        parsedRow.reserve(row.size());

        for (const json& value : row) {
            parsedRow.push_back(readInt(value));
        }

        times.push_back(std::move(parsedRow));
    }

    std::vector<int> throughput;
    throughput.reserve(throughputJson.size());

    for (const json& value : throughputJson) {
        throughput.push_back(readInt(value));
    }

    std::vector<std::pair<std::string, int>> vessels;
    vessels.reserve(inputVessels.size());

    for (const json& item : inputVessels) {
        if (!item.is_object()) {
            throw std::runtime_error("vessel must be an object");
        }

        std::string id = readStringField(item, "id");
        int location = readIntField(item, "location");
        vessels.emplace_back(std::move(id), location);
    }

    engine.initialize(times, throughput, vessels, readManifest(parameters));
}

json parametersOf(const json& input) {
    if (!input.contains("parameters")) {
        throw std::runtime_error("missing parameters");
    }

    if (!input.at("parameters").is_object()) {
        throw std::runtime_error("parameters must be an object");
    }

    return input.at("parameters");
}

json handleCommand(SimulationEngine& engine, const json& input) {
    if (!input.is_object()) {
        throw std::runtime_error("command must be an object");
    }

    if (!input.contains("command")) {
        throw std::runtime_error("missing command");
    }

    if (!input.at("command").is_string()) {
        throw std::runtime_error("command must be a string");
    }

    const std::string command = input.at("command").get<std::string>();
    const json parameters = parametersOf(input);

    if (command == "init") {
        initializeFromJson(engine, parameters);
        return worldToJson(engine.getState());
    }

    if (command == "set_destination") {
        engine.setDestination(
            readStringField(parameters, "vessel_id"),
            readIntField(parameters, "destination")
        );
        return worldToJson(engine.getState());
    }

    if (command == "tick") {
        engine.tick(readManifest(parameters));
        return worldToJson(engine.getState());
    }

    if (command == "get_state") {
        return worldToJson(engine.getState());
    }

    if (command == "dock") {
        engine.dock(readStringField(parameters, "vessel_id"));
        return worldToJson(engine.getState());
    }

    if (command == "undock") {
        engine.undock(readStringField(parameters, "vessel_id"));
        return worldToJson(engine.getState());
    }

    if (command == "load") {
        engine.load(
            readStringField(parameters, "vessel_id"),
            readIntField(parameters, "destination")
        );
        return worldToJson(engine.getState());
    }

    if (command == "unload") {
        engine.unload(
            readStringField(parameters, "vessel_id"),
            readIntField(parameters, "destination")
        );
        return worldToJson(engine.getState());
    }

    if (command == "swap") {
        engine.swapCargo(
            readStringField(parameters, "vessel_id"),
            readIntField(parameters, "load_destination"),
            readIntField(parameters, "unload_destination")
        );
        return worldToJson(engine.getState());
    }

    if (command == "get_state_at") {
        return worldToJson(engine.getStateAt(readIntField(parameters, "tick")));
    }

    throw std::runtime_error("unknown command: " + command);
}

int main() {
    SimulationEngine engine;
    std::string line;

    while (std::getline(std::cin, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }

        try {
            const json input = json::parse(line);
            writeJson({
                {"status", "ok"},
                {"payload", handleCommand(engine, input)}
            });
        }
        catch (const json::parse_error&) {
            writeError("malformed JSON");
        }
        catch (const std::exception& error) {
            writeError(error.what());
        }
    }

    return 0;
}
