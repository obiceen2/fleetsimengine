#pragma once

#include <vector>

enum class VesselStatus {
    Idle,
    Transit,
    Docked
};

struct CargoLot {
    int destination = 0;
    int quantity = 0;
};

struct VesselState {
    VesselStatus status = VesselStatus::Idle;

    int location = 0;
    int from = 0;
    int to = 0;
    int arrivesAtTick = 0;

    std::vector<CargoLot> cargo;
};
