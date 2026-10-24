#include "SimulationEngine.hpp"

#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>

namespace {

int quantityOf(const std::vector<CargoLot>& lots, int destination) {
    for (const CargoLot& lot : lots) {
        if (lot.destination == destination) {
            return lot.quantity;
        }
    }

    return 0;
}

int dockQuantityOf(
    const std::vector<DockCargoLot>& lots,
    int location,
    int destination
) {
    for (const DockCargoLot& lot : lots) {
        if (lot.location == location && lot.destination == destination) {
            return lot.quantity;
        }
    }

    return 0;
}

void addVesselCargo(std::vector<CargoLot>& lots, int destination, int quantity) {
    if (quantity <= 0) {
        throw std::runtime_error("cargo manifest quantity must be positive");
    }

    for (CargoLot& lot : lots) {
        if (lot.destination == destination) {
            if (lot.quantity > std::numeric_limits<int>::max() - quantity) {
                throw std::runtime_error("cargo quantity overflow");
            }

            lot.quantity += quantity;
            return;
        }
    }

    lots.push_back(CargoLot{destination, quantity});
}

void addDockCargo(
    std::vector<DockCargoLot>& lots,
    int location,
    int destination,
    int quantity
) {
    if (quantity <= 0) {
        throw std::runtime_error("cargo manifest quantity must be positive");
    }

    for (DockCargoLot& lot : lots) {
        if (lot.location == location && lot.destination == destination) {
            if (lot.quantity > std::numeric_limits<int>::max() - quantity) {
                throw std::runtime_error("cargo quantity overflow");
            }

            lot.quantity += quantity;
            return;
        }
    }

    lots.push_back(DockCargoLot{location, destination, quantity});
}

bool takeVesselCargo(std::vector<CargoLot>& lots, int destination) {
    for (auto it = lots.begin(); it != lots.end(); ++it) {
        if (it->destination == destination) {
            it->quantity -= 1;

            if (it->quantity == 0) {
                lots.erase(it);
            }

            return true;
        }
    }

    return false;
}

bool takeDockCargo(
    std::vector<DockCargoLot>& lots,
    int location,
    int destination
) {
    for (auto it = lots.begin(); it != lots.end(); ++it) {
        if (it->location == location && it->destination == destination) {
            it->quantity -= 1;

            if (it->quantity == 0) {
                lots.erase(it);
            }

            return true;
        }
    }

    return false;
}

void applyManifest(WorldState& world, const std::vector<ManifestEntry>& manifest) {
    for (const ManifestEntry& entry : manifest) {
        addDockCargo(world.cargo, entry.location, entry.destination, entry.quantity);
    }
}

std::string throughputMessage(long long attempted, int limit, int location) {
    return "transfer of " + std::to_string(attempted) +
           " operations exceeds dock throughput of " + std::to_string(limit) +
           " at location " + std::to_string(location);
}

}

void SimulationEngine::ensureInitialized() const {
    if (!initialized) {
        throw std::runtime_error("simulation not initialized");
    }
}

void SimulationEngine::validateTravelTimes(
    const std::vector<std::vector<int>>& times
) const {
    const std::size_t locations = times.size();

    if (locations == 0) {
        throw std::runtime_error("travel time matrix cannot be empty");
    }

    if (locations > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error("too many locations");
    }

    for (std::size_t from = 0; from < locations; ++from) {
        if (times[from].size() != locations) {
            throw std::runtime_error("travel time matrix must be square");
        }

        for (std::size_t to = 0; to < locations; ++to) {
            if (from == to && times[from][to] != 0) {
                throw std::runtime_error("diagonal travel times must be zero");
            }

            if (from != to && times[from][to] <= 0) {
                throw std::runtime_error("travel times must be positive");
            }
        }
    }
}

void SimulationEngine::validateThroughput(
    const std::vector<int>& throughput,
    std::size_t locations
) const {
    if (throughput.size() != locations) {
        throw std::runtime_error(
            "dock_throughput length must match number of locations"
        );
    }

    for (int limit : throughput) {
        if (limit <= 0) {
            throw std::runtime_error("dock throughput must be positive");
        }
    }
}

void SimulationEngine::validateManifest(
    const std::vector<ManifestEntry>& cargoManifest,
    std::size_t locations
) const {
    for (const ManifestEntry& entry : cargoManifest) {
        if (entry.location < 0 ||
            static_cast<std::size_t>(entry.location) >= locations) {
            throw std::runtime_error("cargo manifest location out of range");
        }

        if (entry.destination < 0 ||
            static_cast<std::size_t>(entry.destination) >= locations) {
            throw std::runtime_error("cargo manifest destination out of range");
        }

        if (entry.quantity <= 0) {
            throw std::runtime_error("cargo manifest quantity must be positive");
        }
    }
}

void SimulationEngine::requireDestination(int destination) const {
    if (destination < 0 ||
        static_cast<std::size_t>(destination) >= travelTimes.size()) {
        throw std::runtime_error("destination out of range");
    }
}

const VesselState& SimulationEngine::requireVessel(
    const std::string& vesselId
) const {
    ensureInitialized();

    auto it = committed.vessels.find(vesselId);

    if (it == committed.vessels.end()) {
        throw std::runtime_error("unknown vessel: " + vesselId);
    }

    return it->second;
}

int SimulationEngine::requireOperatingDock(const std::string& vesselId) const {
    const VesselState& current = requireVessel(vesselId);

    if (current.status != VesselStatus::Docked) {
        throw std::runtime_error("vessel " + vesselId + " is not docked");
    }

    const VesselState& pending = planned.vessels.at(vesselId);

    if (pending.status != VesselStatus::Docked) {
        throw std::runtime_error("vessel " + vesselId + " is pending undock");
    }

    return current.location;
}

void SimulationEngine::ensureOperationAvailable(int location) const {
    const int used = operationsUsed.at(static_cast<std::size_t>(location));
    const int limit = dockThroughput.at(static_cast<std::size_t>(location));
    const long long attempted = static_cast<long long>(used) + 1;

    if (attempted > limit) {
        throw std::runtime_error(throughputMessage(attempted, limit, location));
    }
}

void SimulationEngine::initialize(
    const std::vector<std::vector<int>>& times,
    const std::vector<int>& throughput,
    const std::vector<std::pair<std::string, int>>& vessels,
    const std::vector<ManifestEntry>& cargoManifest
) {
    if (initialized) {
        throw std::runtime_error("simulation already initialized");
    }

    validateTravelTimes(times);
    validateThroughput(throughput, times.size());
    validateManifest(cargoManifest, times.size());

    WorldState initial;
    std::unordered_set<std::string> seenIds;

    for (const auto& [id, location] : vessels) {
        if (!seenIds.insert(id).second) {
            throw std::runtime_error("duplicate vessel id: " + id);
        }

        if (location < 0 || static_cast<std::size_t>(location) >= times.size()) {
            throw std::runtime_error("invalid starting location");
        }

        VesselState vessel;
        vessel.status = VesselStatus::Idle;
        vessel.location = location;
        initial.vessels.emplace(id, vessel);
    }

    initial.tick = 0;
    applyManifest(initial, cargoManifest);

    std::vector<int> unused(times.size(), 0);
    std::vector<WorldState> snapshots;
    snapshots.push_back(initial);

    committed = initial;
    planned = std::move(initial);
    travelTimes = times;
    dockThroughput = throughput;
    operationsUsed = std::move(unused);
    history = std::move(snapshots);
    initialized = true;
}

void SimulationEngine::setDestination(
    const std::string& vesselId,
    int destination
) {
    ensureInitialized();

    const VesselState& current = requireVessel(vesselId);
    requireDestination(destination);

    if (current.status != VesselStatus::Idle) {
        throw std::runtime_error("vessel " + vesselId + " is not idle");
    }

    if (destination == current.location) {
        throw std::runtime_error("destination is current location");
    }

    const int travelTime = travelTimes[current.location][destination];

    if (travelTime > std::numeric_limits<int>::max() - committed.tick) {
        throw std::runtime_error("arrival tick overflow");
    }

    VesselState& next = planned.vessels.at(vesselId);
    next.status = VesselStatus::Transit;
    next.location = current.location;
    next.from = current.location;
    next.to = destination;
    next.arrivesAtTick = committed.tick + travelTime;
}

void SimulationEngine::tick(const std::vector<ManifestEntry>& cargoManifest) {
    ensureInitialized();
    validateManifest(cargoManifest, travelTimes.size());

    if (committed.tick == std::numeric_limits<int>::max()) {
        throw std::runtime_error("simulation tick overflow");
    }

    WorldState next = planned;
    next.tick = committed.tick + 1;

    for (auto& entry : next.vessels) {
        VesselState& vessel = entry.second;

        if (vessel.status == VesselStatus::Transit &&
            vessel.arrivesAtTick <= next.tick) {
            vessel.status = VesselStatus::Idle;
            vessel.location = vessel.to;
        }
    }

    applyManifest(next, cargoManifest);

    std::vector<int> reset(dockThroughput.size(), 0);
    std::vector<WorldState> snapshots = history;
    snapshots.push_back(next);

    committed = next;
    planned = std::move(next);
    operationsUsed = std::move(reset);
    history = std::move(snapshots);
}

void SimulationEngine::dock(const std::string& vesselId) {
    ensureInitialized();

    const VesselState& current = requireVessel(vesselId);

    if (current.status != VesselStatus::Idle) {
        throw std::runtime_error("vessel " + vesselId + " is not idle");
    }

    VesselState& next = planned.vessels.at(vesselId);
    next.status = VesselStatus::Docked;
    next.location = current.location;
}

void SimulationEngine::undock(const std::string& vesselId) {
    ensureInitialized();

    const VesselState& current = requireVessel(vesselId);

    if (current.status != VesselStatus::Docked) {
        throw std::runtime_error("vessel " + vesselId + " is not docked");
    }

    VesselState& next = planned.vessels.at(vesselId);
    next.status = VesselStatus::Idle;
    next.location = current.location;
}

void SimulationEngine::load(const std::string& vesselId, int destination) {
    const int location = requireOperatingDock(vesselId);
    requireDestination(destination);

    WorldState next = planned;
    VesselState& vessel = next.vessels.at(vesselId);

    if (dockQuantityOf(next.cargo, location, destination) < 1) {
        throw std::runtime_error(
            "no cargo destined for " + std::to_string(destination) +
            " at location " + std::to_string(location)
        );
    }

    if (quantityOf(vessel.cargo, destination) == std::numeric_limits<int>::max()) {
        throw std::runtime_error("cargo quantity overflow");
    }

    ensureOperationAvailable(location);

    if (!takeDockCargo(next.cargo, location, destination)) {
        throw std::runtime_error(
            "no cargo destined for " + std::to_string(destination) +
            " at location " + std::to_string(location)
        );
    }

    addVesselCargo(vessel.cargo, destination, 1);

    std::vector<int> used = operationsUsed;
    used.at(static_cast<std::size_t>(location)) += 1;

    planned = std::move(next);
    operationsUsed = std::move(used);
}

void SimulationEngine::unload(const std::string& vesselId, int destination) {
    const int location = requireOperatingDock(vesselId);
    requireDestination(destination);

    WorldState next = planned;
    VesselState& vessel = next.vessels.at(vesselId);

    if (quantityOf(vessel.cargo, destination) < 1) {
        throw std::runtime_error(
            "vessel " + vesselId + " has no cargo destined for " +
            std::to_string(destination)
        );
    }

    const bool deliver = destination == location;

    if (!deliver &&
        dockQuantityOf(next.cargo, location, destination) ==
            std::numeric_limits<int>::max()) {
        throw std::runtime_error("cargo quantity overflow");
    }

    ensureOperationAvailable(location);

    if (!takeVesselCargo(vessel.cargo, destination)) {
        throw std::runtime_error(
            "vessel " + vesselId + " has no cargo destined for " +
            std::to_string(destination)
        );
    }

    if (!deliver) {
        addDockCargo(next.cargo, location, destination, 1);
    }

    std::vector<int> used = operationsUsed;
    used.at(static_cast<std::size_t>(location)) += 1;

    planned = std::move(next);
    operationsUsed = std::move(used);
}

void SimulationEngine::swapCargo(
    const std::string& vesselId,
    int loadDestination,
    int unloadDestination
) {
    const int location = requireOperatingDock(vesselId);
    requireDestination(loadDestination);
    requireDestination(unloadDestination);

    WorldState next = planned;
    VesselState& vessel = next.vessels.at(vesselId);

    if (quantityOf(vessel.cargo, unloadDestination) < 1) {
        throw std::runtime_error(
            "vessel " + vesselId + " has no cargo destined for " +
            std::to_string(unloadDestination)
        );
    }

    if (dockQuantityOf(next.cargo, location, loadDestination) < 1) {
        throw std::runtime_error(
            "no cargo destined for " + std::to_string(loadDestination) +
            " at location " + std::to_string(location)
        );
    }

    const bool deliver = unloadDestination == location;
    const bool sameCargo = loadDestination == unloadDestination;

    if (!sameCargo &&
        quantityOf(vessel.cargo, loadDestination) ==
            std::numeric_limits<int>::max()) {
        throw std::runtime_error("cargo quantity overflow");
    }

    if (!sameCargo && !deliver &&
        dockQuantityOf(next.cargo, location, unloadDestination) ==
            std::numeric_limits<int>::max()) {
        throw std::runtime_error("cargo quantity overflow");
    }

    ensureOperationAvailable(location);

    if (!takeVesselCargo(vessel.cargo, unloadDestination) ||
        !takeDockCargo(next.cargo, location, loadDestination)) {
        throw std::runtime_error("cargo inventory changed during swap");
    }

    if (!deliver) {
        addDockCargo(next.cargo, location, unloadDestination, 1);
    }

    addVesselCargo(vessel.cargo, loadDestination, 1);

    std::vector<int> used = operationsUsed;
    used.at(static_cast<std::size_t>(location)) += 1;

    planned = std::move(next);
    operationsUsed = std::move(used);
}

const WorldState& SimulationEngine::getState() const {
    ensureInitialized();
    return planned;
}

const WorldState& SimulationEngine::getStateAt(int tick) const {
    ensureInitialized();

    if (tick < 0) {
        throw std::runtime_error(
            "tick " + std::to_string(tick) + " is negative"
        );
    }

    if (tick > committed.tick) {
        throw std::runtime_error(
            "tick " + std::to_string(tick) +
            " is in the future (current tick: " +
            std::to_string(committed.tick) + ")"
        );
    }

    return history.at(static_cast<std::size_t>(tick));
}
