#pragma once

#include <map>
#include <string>
#include <vector>

#include "Vessel.hpp"

struct DockCargoLot {
    int location = 0;
    int destination = 0;
    int quantity = 0;
};

struct WorldState {
    int tick = 0;

    std::map<std::string, VesselState> vessels;
    std::vector<DockCargoLot> cargo;
};
