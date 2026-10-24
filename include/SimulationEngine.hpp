#pragma once

#include <string>
#include <utility>
#include <vector>

#include "WorldState.hpp"

struct ManifestEntry {
    int location = 0;
    int destination = 0;
    int quantity = 0;
};

class SimulationEngine {
public:
    void initialize(
        const std::vector<std::vector<int>>& travelTimes,
        const std::vector<int>& dockThroughput,
        const std::vector<std::pair<std::string, int>>& vessels,
        const std::vector<ManifestEntry>& cargoManifest
    );

    void setDestination(const std::string& vesselId, int destination);
    void tick(const std::vector<ManifestEntry>& cargoManifest);
    void dock(const std::string& vesselId);
    void undock(const std::string& vesselId);
    void load(const std::string& vesselId, int destination);
    void unload(const std::string& vesselId, int destination);
    void swapCargo(
        const std::string& vesselId,
        int loadDestination,
        int unloadDestination
    );

    const WorldState& getState() const;
    const WorldState& getStateAt(int tick) const;

private:
    void ensureInitialized() const;
    void validateTravelTimes(
        const std::vector<std::vector<int>>& travelTimes
    ) const;
    void validateThroughput(
        const std::vector<int>& dockThroughput,
        std::size_t locations
    ) const;
    void validateManifest(
        const std::vector<ManifestEntry>& cargoManifest,
        std::size_t locations
    ) const;
    void requireDestination(int destination) const;

    const VesselState& requireVessel(const std::string& vesselId) const;
    int requireOperatingDock(const std::string& vesselId) const;
    void ensureOperationAvailable(int location) const;

    bool initialized = false;

    WorldState committed;
    WorldState planned;

    std::vector<std::vector<int>> travelTimes;
    std::vector<int> dockThroughput;
    std::vector<int> operationsUsed;
    std::vector<WorldState> history;
};
