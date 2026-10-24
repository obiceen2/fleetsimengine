import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMES = [[0, 4, 7], [4, 0, 3], [7, 3, 0]]
THROUGHPUT = [2, 4, 1]
INT_MAX = 2147483647


def simulator_path():
    override = os.environ.get("SIMULATOR")
    if override:
        return override

    for directory in (ROOT / "build", ROOT / "build" / "Debug", ROOT / "build" / "Release"):
        for name in ("simulator", "simulator.exe"):
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)

    raise FileNotFoundError(
        "simulator executable not found; configure and build the project first"
    )


def idle(location, cargo=None):
    return {
        "state": "idle",
        "location": location,
        "cargo": [] if cargo is None else cargo,
    }


def docked(location, cargo=None):
    return {
        "state": "docked",
        "location": location,
        "cargo": [] if cargo is None else cargo,
    }


def transit(origin, destination, arrives, cargo=None):
    return {
        "state": "transit",
        "from": origin,
        "to": destination,
        "arrives_at_tick": arrives,
        "cargo": [] if cargo is None else cargo,
    }


def lot(destination, quantity=1):
    return {"destination": destination, "quantity": quantity}


def dock_lot(location, destination, quantity=1):
    return {
        "location": location,
        "destination": destination,
        "quantity": quantity,
    }


def world(tick, vessels, cargo=None):
    return {
        "tick": tick,
        "vessels": vessels,
        "cargo": [] if cargo is None else cargo,
    }


def pair(tick, v1, cargo=None, v2=None):
    return world(tick, {"v1": v1, "v2": idle(2) if v2 is None else v2}, cargo)


def command(name, **parameters):
    return json.dumps(
        {"command": name, "parameters": parameters},
        separators=(",", ":"),
    )


def init_command(
    manifest=None,
    throughput=None,
    vessels=None,
    times=None,
    extra=None,
):
    parameters = {
        "travel_times": TIMES if times is None else times,
        "dock_throughput": THROUGHPUT if throughput is None else throughput,
        "vessels": [
            {"id": "v1", "location": 0},
            {"id": "v2", "location": 2},
        ]
        if vessels is None
        else vessels,
    }
    if manifest is not None:
        parameters["cargo_manifest"] = manifest
    if extra:
        parameters.update(extra)
    return json.dumps(
        {"command": "init", "parameters": parameters},
        separators=(",", ":"),
    )


class SimulatorCase(unittest.TestCase):
    def run_lines(self, lines):
        completed = subprocess.run(
            [simulator_path()],
            input="".join(f"{line}\n" for line in lines),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        output_lines = completed.stdout.splitlines()
        self.assertEqual(len(output_lines), len(lines), completed.stdout)
        parsed = []
        for line in output_lines:
            parsed.append(json.loads(line))
            self.assertEqual(set(parsed[-1]), {"status", "payload"})
        return parsed

    def assert_ok(self, response, payload):
        self.assertEqual(response, {"status": "ok", "payload": payload})

    def assert_error(self, response, message):
        self.assertEqual(
            response,
            {"status": "error", "payload": {"message": message}},
        )


class BaseSimulationTests(SimulatorCase):
    def test_successful_initialization(self):
        responses = self.run_lines([init_command(), command("get_state")])
        expected = pair(0, idle(0))
        self.assert_ok(responses[0], expected)
        self.assert_ok(responses[1], expected)

    def test_initialization_accepts_extra_fields(self):
        responses = self.run_lines([
            init_command(extra={"note": "ignored"}),
        ])
        self.assert_ok(responses[0], pair(0, idle(0)))

    def test_empty_fleet_is_valid(self):
        responses = self.run_lines([
            init_command(vessels=[], throughput=[1], times=[[0]]),
            command("tick"),
        ])
        self.assert_ok(responses[0], world(0, {}))
        self.assert_ok(responses[1], world(1, {}))

    def test_invalid_initialization_cases(self):
        cases = [
            (init_command(times=[]), "travel time matrix cannot be empty"),
            (
                init_command(times=[[0, 1], [1]]),
                "travel time matrix must be square",
            ),
            (init_command(times=[[1]]), "diagonal travel times must be zero"),
            (
                init_command(times=[[0, 0], [1, 0]]),
                "travel times must be positive",
            ),
            (
                init_command(times=[[0, -1], [1, 0]]),
                "travel times must be positive",
            ),
            (
                init_command(vessels=[
                    {"id": "v1", "location": 0},
                    {"id": "v1", "location": 1},
                ]),
                "duplicate vessel id: v1",
            ),
            (
                init_command(vessels=[{"id": "v1", "location": 3}]),
                "invalid starting location",
            ),
            (
                init_command(vessels=[{"id": "v1", "location": -1}]),
                "invalid starting location",
            ),
            (
                init_command(throughput=[2, 4]),
                "dock_throughput length must match number of locations",
            ),
            (
                init_command(throughput=[2, 0, 1]),
                "dock throughput must be positive",
            ),
            (
                init_command(throughput=[2, -4, 1]),
                "dock throughput must be positive",
            ),
            (
                init_command(manifest=[
                    {"location": 9, "destination": 0, "quantity": 1},
                ]),
                "cargo manifest location out of range",
            ),
            (
                init_command(manifest=[
                    {"location": 0, "destination": -1, "quantity": 1},
                ]),
                "cargo manifest destination out of range",
            ),
            (
                init_command(manifest=[
                    {"location": 0, "destination": 1, "quantity": 0},
                ]),
                "cargo manifest quantity must be positive",
            ),
            (
                init_command(manifest=[
                    {"location": 0, "destination": 1, "quantity": -5},
                ]),
                "cargo manifest quantity must be positive",
            ),
        ]

        probing_init = init_command()
        for bad, message in cases:
            with self.subTest(message=message):
                responses = self.run_lines([
                    bad,
                    command("get_state"),
                    probing_init,
                ])
                self.assert_error(responses[0], message)
                self.assert_error(responses[1], "simulation not initialized")
                self.assert_ok(responses[2], pair(0, idle(0)))

    def test_malformed_init_shapes(self):
        cases = [
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "dock_throughput": THROUGHPUT,
                        "vessels": [],
                    },
                }),
                "missing travel_times",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": TIMES,
                        "vessels": [],
                    },
                }),
                "missing dock_throughput",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": TIMES,
                        "dock_throughput": THROUGHPUT,
                    },
                }),
                "missing vessels",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": {"0": [0]},
                        "dock_throughput": [1],
                        "vessels": [],
                    },
                }),
                "travel_times must be an array",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": 1,
                        "vessels": [],
                    },
                }),
                "dock_throughput must be an array",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [1],
                        "vessels": {},
                    },
                }),
                "vessels must be an array",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [0],
                        "dock_throughput": [1],
                        "vessels": [],
                    },
                }),
                "each travel time row must be an array",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0.5]],
                        "dock_throughput": [1],
                        "vessels": [],
                    },
                }),
                "expected integer",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[True]],
                        "dock_throughput": [1],
                        "vessels": [],
                    },
                }),
                "expected integer",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [1],
                        "vessels": ["v1"],
                    },
                }),
                "vessel must be an object",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [1],
                        "vessels": [{"location": 0}],
                    },
                }),
                "missing id",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [1],
                        "vessels": [{"id": 1, "location": 0}],
                    },
                }),
                "id must be a string",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [1],
                        "vessels": [{"id": "v1"}],
                    },
                }),
                "missing location",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [1],
                        "vessels": [{"id": "v1", "location": "0"}],
                    },
                }),
                "expected integer",
            ),
            (
                json.dumps({
                    "command": "init",
                    "parameters": {
                        "travel_times": [[0]],
                        "dock_throughput": [4294967296],
                        "vessels": [],
                    },
                }),
                "integer out of range",
            ),
        ]

        for bad, message in cases:
            with self.subTest(message=message):
                responses = self.run_lines([bad, init_command(vessels=[], throughput=[1], times=[[0]])])
                self.assert_error(responses[0], message)
                self.assertEqual(responses[1]["status"], "ok")

    def test_duplicate_initialization_preserves_state(self):
        first = init_command(manifest=[
            {"location": 0, "destination": 2, "quantity": 2},
        ])
        second = init_command()
        responses = self.run_lines([first, second, command("get_state")])
        expected = pair(0, idle(0), [dock_lot(0, 2, 2)])
        self.assert_ok(responses[0], expected)
        self.assert_error(responses[1], "simulation already initialized")
        self.assert_ok(responses[2], expected)

    def test_multiple_vessels_move_independently(self):
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=1),
            command("set_destination", vessel_id="v2", destination=1),
            command("tick"),
        ])
        self.assert_ok(responses[1], pair(0, transit(0, 1, 4)))
        self.assert_ok(
            responses[2],
            pair(0, transit(0, 1, 4), v2=transit(2, 1, 3)),
        )
        self.assert_ok(
            responses[3],
            pair(1, transit(0, 1, 4), v2=transit(2, 1, 3)),
        )

    def test_destination_override_before_tick(self):
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=2),
            command("set_destination", vessel_id="v1", destination=1),
        ])
        self.assert_ok(responses[1], pair(0, transit(0, 2, 7)))
        self.assert_ok(responses[2], pair(0, transit(0, 1, 4)))

    def test_redirect_rejected_after_committed_transit(self):
        planned = pair(1, transit(0, 1, 4))
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick"),
            command("set_destination", vessel_id="v1", destination=2),
            command("get_state"),
        ])
        self.assert_ok(responses[2], planned)
        self.assert_error(responses[3], "vessel v1 is not idle")
        self.assert_ok(responses[4], planned)

    def test_exact_arrival_and_immediate_command(self):
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick"),
            command("tick"),
            command("tick"),
            command("tick"),
            command("set_destination", vessel_id="v1", destination=2),
            command("tick"),
            command("dock", vessel_id="v1"),
        ])
        self.assert_ok(responses[2], pair(1, transit(0, 1, 4)))
        self.assert_ok(responses[3], pair(2, transit(0, 1, 4)))
        self.assert_ok(responses[4], pair(3, transit(0, 1, 4)))
        self.assert_ok(responses[5], pair(4, idle(1)))
        self.assert_ok(responses[6], pair(4, transit(1, 2, 7)))
        self.assert_ok(responses[7], pair(5, transit(1, 2, 7)))
        self.assert_error(responses[8], "vessel v1 is not idle")

    def test_travel_time_one_arrives_on_next_tick(self):
        responses = self.run_lines([
            init_command(
                times=[[0, 1], [1, 0]],
                throughput=[1, 1],
                vessels=[{"id": "v1", "location": 0}],
            ),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick"),
            command("dock", vessel_id="v1"),
        ])
        self.assert_ok(
            responses[1],
            world(0, {"v1": transit(0, 1, 1)}),
        )
        self.assert_ok(responses[2], world(1, {"v1": idle(1)}))
        self.assert_ok(responses[3], world(1, {"v1": docked(1)}))

    def test_unknown_vessel_and_invalid_destination(self):
        idle_world = pair(0, idle(0))
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="missing", destination=1),
            command("set_destination", vessel_id="v1", destination=-1),
            command("set_destination", vessel_id="v1", destination=3),
            command("set_destination", vessel_id="v1", destination=0),
            command("get_state"),
        ])
        self.assert_error(responses[1], "unknown vessel: missing")
        self.assert_error(responses[2], "destination out of range")
        self.assert_error(responses[3], "destination out of range")
        self.assert_error(responses[4], "destination is current location")
        self.assert_ok(responses[5], idle_world)

    def test_same_location_does_not_clear_pending_transit(self):
        pending = pair(0, transit(0, 1, 4))
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=1),
            command("set_destination", vessel_id="v1", destination=0),
            command("get_state"),
        ])
        self.assert_error(responses[2], "destination is current location")
        self.assert_ok(responses[3], pending)

    def test_arrival_tick_overflow_preserves_state(self):
        responses = self.run_lines([
            init_command(
                times=[[0, INT_MAX], [INT_MAX, 0]],
                throughput=[1, 1],
                vessels=[{"id": "v1", "location": 0}],
            ),
            command("tick"),
            command("set_destination", vessel_id="v1", destination=1),
            command("get_state"),
        ])
        self.assert_error(responses[2], "arrival tick overflow")
        self.assert_ok(responses[3], world(1, {"v1": idle(0)}))

    def test_maximum_travel_time_is_representable_at_tick_zero(self):
        responses = self.run_lines([
            init_command(
                times=[[0, INT_MAX], [INT_MAX, 0]],
                throughput=[1, 1],
                vessels=[{"id": "v1", "location": 0}],
            ),
            command("set_destination", vessel_id="v1", destination=1),
        ])
        self.assert_ok(
            responses[1],
            world(0, {"v1": transit(0, 1, INT_MAX)}),
        )

    def test_base_example_from_spec(self):
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=2),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick"),
            command("set_destination", vessel_id="v1", destination=2),
            command("tick"),
            command("tick"),
            command("tick"),
            command("set_destination", vessel_id="v1", destination=2),
        ])
        self.assert_ok(responses[0], pair(0, idle(0)))
        self.assert_ok(responses[1], pair(0, transit(0, 2, 7)))
        self.assert_ok(responses[2], pair(0, transit(0, 1, 4)))
        self.assert_ok(responses[3], pair(1, transit(0, 1, 4)))
        self.assert_error(responses[4], "vessel v1 is not idle")
        self.assert_ok(responses[5], pair(2, transit(0, 1, 4)))
        self.assert_ok(responses[6], pair(3, transit(0, 1, 4)))
        self.assert_ok(responses[7], pair(4, idle(1)))
        self.assert_ok(responses[8], pair(4, transit(1, 2, 7)))


class DockingTests(SimulatorCase):
    def test_idle_to_docked_and_back(self):
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("undock", vessel_id="v1"),
            command("tick"),
        ])
        self.assert_ok(responses[1], pair(0, docked(0)))
        self.assert_ok(responses[2], pair(1, docked(0)))
        self.assert_ok(responses[3], pair(1, idle(0)))
        self.assert_ok(responses[4], pair(2, idle(0)))

    def test_invalid_dock_and_undock(self):
        responses = self.run_lines([
            init_command(),
            command("undock", vessel_id="v1"),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick"),
            command("dock", vessel_id="v1"),
            command("undock", vessel_id="v1"),
            command("dock", vessel_id="missing"),
            command("undock", vessel_id="missing"),
            command("get_state"),
        ])
        self.assert_error(responses[1], "vessel v1 is not docked")
        self.assert_error(responses[4], "vessel v1 is not idle")
        self.assert_error(responses[5], "vessel v1 is not docked")
        self.assert_error(responses[6], "unknown vessel: missing")
        self.assert_error(responses[7], "unknown vessel: missing")
        self.assert_ok(responses[8], pair(1, transit(0, 1, 4)))

    def test_pending_dock_and_destination_override_each_other(self):
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=1),
            command("dock", vessel_id="v1"),
            command("set_destination", vessel_id="v1", destination=2),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("get_state_at", tick=0),
            command("get_state_at", tick=1),
        ])
        self.assert_ok(responses[1], pair(0, transit(0, 1, 4)))
        self.assert_ok(responses[2], pair(0, docked(0)))
        self.assert_ok(responses[3], pair(0, transit(0, 2, 7)))
        self.assert_ok(responses[4], pair(0, docked(0)))
        self.assert_ok(responses[5], pair(1, docked(0)))
        self.assert_ok(responses[6], pair(0, idle(0)))
        self.assert_ok(responses[7], pair(1, docked(0)))

    def test_repeated_pending_dock_is_idempotent(self):
        docked_world = pair(0, docked(0))
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("dock", vessel_id="v1"),
            command("get_state"),
        ])
        self.assert_ok(responses[1], docked_world)
        self.assert_ok(responses[2], docked_world)
        self.assert_ok(responses[3], docked_world)

    def test_dock_after_committed_dock_is_rejected(self):
        committed = pair(1, docked(0))
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("dock", vessel_id="v1"),
            command("get_state"),
        ])
        self.assert_error(responses[3], "vessel v1 is not idle")
        self.assert_ok(responses[4], committed)

    def test_undock_after_pending_dock_is_rejected(self):
        pending = pair(0, docked(0))
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("undock", vessel_id="v1"),
            command("get_state"),
        ])
        self.assert_error(responses[2], "vessel v1 is not docked")
        self.assert_ok(responses[3], pending)

    def test_repeated_pending_undock_is_idempotent(self):
        pending = pair(1, idle(0))
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("undock", vessel_id="v1"),
            command("undock", vessel_id="v1"),
            command("get_state"),
        ])
        self.assert_ok(responses[3], pending)
        self.assert_ok(responses[4], pending)
        self.assert_ok(responses[5], pending)

    def test_dock_after_pending_undock_is_rejected(self):
        pending = pair(1, idle(0))
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("undock", vessel_id="v1"),
            command("dock", vessel_id="v1"),
            command("set_destination", vessel_id="v1", destination=1),
            command("get_state"),
        ])
        self.assert_error(responses[4], "vessel v1 is not idle")
        self.assert_error(responses[5], "vessel v1 is not idle")
        self.assert_ok(responses[6], pending)

    def test_cargo_operation_requires_committed_dock(self):
        pending_dock = pair(0, docked(0), [dock_lot(0, 1)])
        responses = self.run_lines([
            init_command(manifest=[{"location": 0, "destination": 1, "quantity": 1}]),
            command("dock", vessel_id="v1"),
            command("load", vessel_id="v1", destination=1),
            command("get_state"),
        ])
        self.assert_error(responses[2], "vessel v1 is not docked")
        self.assert_ok(responses[3], pending_dock)


class CargoTests(SimulatorCase):
    def test_initial_manifest_preserves_order_and_aggregates(self):
        manifest = [
            {"location": 0, "destination": 2, "quantity": 1},
            {"location": 0, "destination": 1, "quantity": 1},
            {"location": 2, "destination": 0, "quantity": 1},
            {"location": 0, "destination": 2, "quantity": 3},
        ]
        responses = self.run_lines([init_command(manifest=manifest)])
        self.assert_ok(responses[0], pair(0, idle(0), [
            dock_lot(0, 2, 4),
            dock_lot(0, 1, 1),
            dock_lot(2, 0, 1),
        ]))

    def test_tick_manifest_adds_to_committed_state_and_rejects_atomically(self):
        initial = [
            {"location": 0, "destination": 2, "quantity": 1},
        ]
        added = [
            {"location": 0, "destination": 2, "quantity": 2},
            {"location": 2, "destination": 0, "quantity": 1},
        ]
        bad = [
            {"location": 0, "destination": 1, "quantity": 1},
            {"location": 5, "destination": 0, "quantity": 1},
        ]
        start = pair(0, transit(0, 1, 4), [dock_lot(0, 2, 1)])
        responses = self.run_lines([
            init_command(manifest=initial),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick", cargo_manifest=bad),
            command("get_state"),
            command("tick", cargo_manifest=added),
        ])
        self.assert_error(responses[2], "cargo manifest location out of range")
        self.assert_ok(responses[3], start)
        self.assert_ok(responses[4], pair(1, transit(0, 1, 4), [
            dock_lot(0, 2, 3),
            dock_lot(2, 0, 1),
        ]))

    def test_manifest_quantity_overflow_does_not_tick(self):
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": INT_MAX},
            ]),
            command("tick", cargo_manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("get_state"),
        ])
        expected = pair(0, idle(0), [dock_lot(0, 1, INT_MAX)])
        self.assert_error(responses[1], "cargo quantity overflow")
        self.assert_ok(responses[2], expected)

    def test_manifest_shape_errors(self):
        cases = [
            (command("tick", cargo_manifest={"location": 0}), "cargo_manifest must be an array"),
            (
                command("tick", cargo_manifest=["nope"]),
                "cargo manifest entry must be an object",
            ),
            (
                command("tick", cargo_manifest=[{"destination": 1, "quantity": 1}]),
                "missing location",
            ),
            (
                command("tick", cargo_manifest=[{"location": 0, "quantity": 1}]),
                "missing destination",
            ),
            (
                command("tick", cargo_manifest=[{"location": 0, "destination": 1}]),
                "missing quantity",
            ),
        ]
        for bad, message in cases:
            with self.subTest(message=message):
                responses = self.run_lines([init_command(), bad, command("get_state")])
                self.assert_error(responses[1], message)
                self.assert_ok(responses[2], pair(0, idle(0)))

    def test_load_unload_and_partial_quantity(self):
        responses = self.run_lines([
            init_command(
                throughput=[4, 4, 1],
                manifest=[
                    {"location": 0, "destination": 2, "quantity": 2},
                    {"location": 0, "destination": 1, "quantity": 1},
                ],
            ),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=2),
            command("load", vessel_id="v1", destination=2),
            command("unload", vessel_id="v1", destination=2),
        ])
        self.assert_ok(responses[3], pair(1, docked(0, [lot(2)]), [
            dock_lot(0, 2, 1),
            dock_lot(0, 1, 1),
        ]))
        self.assert_ok(responses[4], pair(1, docked(0, [lot(2, 2)]), [
            dock_lot(0, 1, 1),
        ]))
        self.assert_ok(responses[5], pair(1, docked(0, [lot(2)]), [
            dock_lot(0, 1, 1),
            dock_lot(0, 2, 1),
        ]))

    def test_delivery_removes_cargo_from_simulation(self):
        carried = [lot(2), lot(1)]
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 2, "quantity": 1},
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=2),
            command("load", vessel_id="v1", destination=1),
            command("tick"),
            command("undock", vessel_id="v1"),
            command("tick"),
            command("set_destination", vessel_id="v1", destination=2),
            command("tick"),
            command("tick"),
            command("tick"),
            command("tick"),
            command("tick"),
            command("tick"),
            command("tick"),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("unload", vessel_id="v1", destination=2),
            command("tick"),
            command("get_state"),
        ])
        self.assert_ok(responses[5], pair(2, docked(0, carried)))
        self.assert_ok(responses[8], pair(3, transit(0, 2, 10, carried)))
        self.assert_ok(responses[15], pair(10, idle(2, carried)))
        self.assert_ok(responses[17], pair(11, docked(2, carried)))
        self.assert_ok(responses[18], pair(11, docked(2, [lot(1)])))
        self.assert_ok(responses[19], pair(12, docked(2, [lot(1)])))
        self.assert_ok(responses[20], pair(12, docked(2, [lot(1)])))

    def test_unload_elsewhere_returns_cargo_to_that_dock(self):
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("unload", vessel_id="v1", destination=1),
        ])
        self.assert_ok(responses[4], pair(1, docked(0), [dock_lot(0, 1, 1)]))

    def test_swap_exchanges_one_unit_and_is_one_operation(self):
        responses = self.run_lines([
            init_command(
                throughput=[1, 4, 1],
                manifest=[{"location": 0, "destination": 1, "quantity": 1}],
            ),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("tick", cargo_manifest=[
                {"location": 0, "destination": 2, "quantity": 1},
            ]),
            command("swap", vessel_id="v1", load_destination=2, unload_destination=1),
            command("load", vessel_id="v1", destination=1),
        ])
        self.assert_ok(responses[5], pair(2, docked(0, [lot(2)]), [dock_lot(0, 1, 1)]))
        self.assert_error(
            responses[6],
            "transfer of 2 operations exceeds dock throughput of 1 at location 0",
        )

    def test_swap_can_deliver(self):
        responses = self.run_lines([
            init_command(
                times=[[0, 1], [1, 0]],
                throughput=[2, 2],
                vessels=[{"id": "v1", "location": 0}],
                manifest=[
                    {"location": 0, "destination": 0, "quantity": 1},
                    {"location": 0, "destination": 1, "quantity": 1},
                ],
            ),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=0),
            command("tick"),
            command("swap", vessel_id="v1", load_destination=1, unload_destination=0),
        ])
        self.assert_ok(
            responses[5],
            world(2, {"v1": docked(0, [lot(1)])}),
        )

    def test_swap_of_same_cargo_is_atomic_and_net_neutral(self):
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("tick", cargo_manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("swap", vessel_id="v1", load_destination=1, unload_destination=1),
        ])
        self.assert_ok(responses[5], pair(2, docked(0, [lot(1)]), [dock_lot(0, 1, 1)]))

    def test_missing_inventory_does_not_consume_throughput(self):
        loaded = pair(1, docked(0, [lot(1)]))
        responses = self.run_lines([
            init_command(
                throughput=[1, 4, 1],
                manifest=[{"location": 0, "destination": 1, "quantity": 1}],
            ),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=2),
            command("unload", vessel_id="v1", destination=2),
            command("swap", vessel_id="v1", load_destination=1, unload_destination=2),
            command("load", vessel_id="v1", destination=1),
            command("get_state"),
        ])
        self.assert_error(responses[3], "no cargo destined for 2 at location 0")
        self.assert_error(responses[4], "vessel v1 has no cargo destined for 2")
        self.assert_error(responses[5], "vessel v1 has no cargo destined for 2")
        self.assert_ok(responses[6], loaded)
        self.assert_ok(responses[7], loaded)

    def test_failed_swap_does_not_move_either_side(self):
        before = pair(2, docked(0, [lot(2)]), [dock_lot(0, 1, 1)])
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
                {"location": 0, "destination": 2, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=2),
            command("tick"),
            command("swap", vessel_id="v1", load_destination=2, unload_destination=1),
            command("get_state"),
            command("unload", vessel_id="v1", destination=2),
        ])
        self.assert_error(responses[5], "vessel v1 has no cargo destined for 1")
        self.assert_ok(responses[6], before)
        self.assert_ok(responses[7], pair(2, docked(0), [
            dock_lot(0, 1, 1),
            dock_lot(0, 2, 1),
        ]))

    def test_swap_missing_dock_cargo_leaves_vessel_unchanged(self):
        before = pair(1, docked(0, [lot(2)]))
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 2, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=2),
            command("swap", vessel_id="v1", load_destination=1, unload_destination=2),
            command("get_state"),
        ])
        self.assert_error(responses[4], "no cargo destined for 1 at location 0")
        self.assert_ok(responses[5], before)

    def test_throughput_boundary_and_reset(self):
        after_two = pair(1, docked(0, [lot(2), lot(1)]), [dock_lot(0, 0, 1)])
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 2, "quantity": 1},
                {"location": 0, "destination": 1, "quantity": 1},
                {"location": 0, "destination": 0, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=2),
            command("load", vessel_id="v1", destination=1),
            command("load", vessel_id="v1", destination=0),
            command("tick"),
            command("load", vessel_id="v1", destination=0),
        ])
        self.assert_ok(responses[4], after_two)
        self.assert_error(
            responses[5],
            "transfer of 3 operations exceeds dock throughput of 2 at location 0",
        )
        self.assert_ok(
            responses[6],
            pair(2, docked(0, [lot(2), lot(1)]), [dock_lot(0, 0, 1)]),
        )
        self.assert_ok(responses[7], pair(2, docked(0, [lot(2), lot(1), lot(0)])))

    def test_same_cargo_load_and_unload_count_as_two_operations(self):
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("unload", vessel_id="v1", destination=1),
            command("load", vessel_id="v1", destination=1),
        ])
        self.assert_ok(responses[4], pair(1, docked(0), [dock_lot(0, 1, 1)]))
        self.assert_error(
            responses[5],
            "transfer of 3 operations exceeds dock throughput of 2 at location 0",
        )

    def test_shared_throughput_across_vessels(self):
        vessels = [
            {"id": "v1", "location": 0},
            {"id": "v2", "location": 0},
        ]
        both_docked = world(1, {
            "v1": docked(0, [lot(1)]),
            "v2": docked(0),
        }, [dock_lot(0, 1, 1)])
        responses = self.run_lines([
            init_command(
                times=[[0, 1], [1, 0]],
                throughput=[1, 1],
                vessels=vessels,
                manifest=[{"location": 0, "destination": 1, "quantity": 2}],
            ),
            command("dock", vessel_id="v1"),
            command("dock", vessel_id="v2"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("load", vessel_id="v2", destination=1),
            command("tick"),
            command("load", vessel_id="v2", destination=1),
        ])
        self.assert_ok(responses[4], both_docked)
        self.assert_error(
            responses[5],
            "transfer of 2 operations exceeds dock throughput of 1 at location 0",
        )
        self.assert_ok(responses[7], world(2, {
            "v1": docked(0, [lot(1)]),
            "v2": docked(0, [lot(1)]),
        }))

    def test_docks_do_not_share_throughput(self):
        responses = self.run_lines([
            init_command(
                throughput=[1, 1, 1],
                manifest=[
                    {"location": 0, "destination": 1, "quantity": 1},
                    {"location": 2, "destination": 0, "quantity": 1},
                ],
            ),
            command("dock", vessel_id="v1"),
            command("dock", vessel_id="v2"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("load", vessel_id="v2", destination=0),
        ])
        self.assert_ok(responses[5], pair(
            1,
            docked(0, [lot(1)]),
            v2=docked(2, [lot(0)]),
        ))

    def test_inventory_error_wins_when_throughput_is_also_exhausted(self):
        responses = self.run_lines([
            init_command(
                throughput=[1, 4, 1],
                manifest=[{"location": 0, "destination": 1, "quantity": 1}],
            ),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("load", vessel_id="v1", destination=2),
        ])
        self.assert_error(responses[4], "no cargo destined for 2 at location 0")

    def test_undock_keeps_pending_cargo_and_blocks_more_operations(self):
        moved = pair(1, idle(0, [lot(1)]))
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("undock", vessel_id="v1"),
            command("load", vessel_id="v1", destination=1),
            command("get_state"),
            command("get_state_at", tick=1),
            command("tick"),
        ])
        self.assert_error(responses[5], "vessel v1 is pending undock")
        self.assert_ok(responses[6], moved)
        self.assert_ok(responses[7], pair(1, docked(0), [dock_lot(0, 1, 1)]))
        self.assert_ok(responses[8], pair(2, idle(0, [lot(1)])))

    def test_destination_range_checked_before_inventory(self):
        responses = self.run_lines([
            init_command(),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=-1),
            command("unload", vessel_id="v1", destination=9),
            command(
                "swap",
                vessel_id="v1",
                load_destination=1,
                unload_destination=-3,
            ),
        ])
        self.assert_error(responses[3], "destination out of range")
        self.assert_error(responses[4], "destination out of range")
        self.assert_error(responses[5], "destination out of range")

    def test_unload_overflow_restores_nothing(self):
        manifest = [{"location": 0, "destination": 1, "quantity": INT_MAX}]
        responses = self.run_lines([
            init_command(manifest=manifest),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("tick", cargo_manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("unload", vessel_id="v1", destination=1),
            command("get_state"),
        ])
        expected = pair(2, docked(0, [lot(1)]), [dock_lot(0, 1, INT_MAX)])
        self.assert_error(responses[5], "cargo quantity overflow")
        self.assert_ok(responses[6], expected)

    def test_pdf_init_manifest_example(self):
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 2, "quantity": 1},
                {"location": 0, "destination": 1, "quantity": 1},
                {"location": 2, "destination": 0, "quantity": 1},
            ]),
        ])
        self.assert_ok(responses[0], pair(0, idle(0), [
            dock_lot(0, 2, 1),
            dock_lot(0, 1, 1),
            dock_lot(2, 0, 1),
        ]))


class HistoryTests(SimulatorCase):
    def test_tick_zero_and_committed_snapshots_exclude_plans(self):
        dock_cargo = [dock_lot(0, 2, 1), dock_lot(0, 1, 1)]
        responses = self.run_lines([
            init_command(),
            command("get_state_at", tick=0),
            command("tick", cargo_manifest=[
                {"location": 0, "destination": 2, "quantity": 1},
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("get_state_at", tick=0),
            command("get_state_at", tick=1),
            command("get_state"),
        ])
        self.assert_ok(responses[1], pair(0, idle(0)))
        self.assert_ok(responses[4], pair(0, idle(0)))
        self.assert_ok(responses[5], pair(1, idle(0), dock_cargo))
        self.assert_ok(responses[6], pair(1, docked(0), dock_cargo))

    def test_current_tick_query_stays_at_committed_state(self):
        responses = self.run_lines([
            init_command(manifest=[
                {"location": 0, "destination": 1, "quantity": 1},
            ]),
            command("dock", vessel_id="v1"),
            command("tick"),
            command("load", vessel_id="v1", destination=1),
            command("get_state_at", tick=1),
            command("get_state"),
        ])
        self.assert_ok(
            responses[4],
            pair(1, docked(0), [dock_lot(0, 1, 1)]),
        )
        self.assert_ok(responses[5], pair(1, docked(0, [lot(1)])))

    def test_invalid_historical_queries_do_not_change_state(self):
        current = pair(1, transit(0, 1, 4))
        responses = self.run_lines([
            init_command(),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick"),
            command("get_state_at", tick=-1),
            command("get_state_at", tick=2),
            command("get_state_at", tick=99),
            command("get_state"),
            command("get_state_at", tick=1),
        ])
        self.assert_error(responses[3], "tick -1 is negative")
        self.assert_error(responses[4], "tick 2 is in the future (current tick: 1)")
        self.assert_error(responses[5], "tick 99 is in the future (current tick: 1)")
        self.assert_ok(responses[6], current)
        self.assert_ok(responses[7], current)

    def test_history_records_arrival_and_manifest_together(self):
        responses = self.run_lines([
            init_command(
                times=[[0, 1], [1, 0]],
                throughput=[1, 1],
                vessels=[{"id": "v1", "location": 0}],
            ),
            command("set_destination", vessel_id="v1", destination=1),
            command("tick", cargo_manifest=[
                {"location": 1, "destination": 0, "quantity": 4},
            ]),
            command("get_state_at", tick=0),
            command("get_state_at", tick=1),
        ])
        self.assert_ok(responses[3], world(0, {"v1": idle(0)}))
        self.assert_ok(
            responses[4],
            world(1, {"v1": idle(1)}, [dock_lot(1, 0, 4)]),
        )

    def test_queries_do_not_append_history(self):
        responses = self.run_lines([
            init_command(),
            command("get_state_at", tick=0),
            command("get_state"),
            command("get_state_at", tick=1),
            command("tick"),
            command("get_state_at", tick=1),
        ])
        self.assert_error(responses[3], "tick 1 is in the future (current tick: 0)")
        self.assert_ok(responses[4], pair(1, idle(0)))
        self.assert_ok(responses[5], pair(1, idle(0)))


class ProtocolTests(SimulatorCase):
    def test_commands_before_initialization(self):
        lines = [
            command("tick"),
            command("get_state"),
            command("set_destination", vessel_id="v1", destination=1),
            command("dock", vessel_id="v1"),
            command("undock", vessel_id="v1"),
            command("load", vessel_id="v1", destination=1),
            command("unload", vessel_id="v1", destination=1),
            command("swap", vessel_id="v1", load_destination=1, unload_destination=0),
            command("get_state_at", tick=0),
            init_command(),
        ]
        responses = self.run_lines(lines)
        for response in responses[:-1]:
            self.assert_error(response, "simulation not initialized")
        self.assert_ok(responses[-1], pair(0, idle(0)))

    def test_unknown_and_malformed_commands_continue(self):
        responses = self.run_lines([
            "{",
            "",
            "[]",
            "null",
            "42",
            '"init"',
            json.dumps({"parameters": {}}),
            json.dumps({"command": 1, "parameters": {}}),
            json.dumps({"command": "init", "parameters": []}),
            json.dumps({"command": "TICK", "parameters": {}}),
            json.dumps({"command": "frob", "parameters": {}}),
            init_command(),
            json.dumps({"command": "get_state", "parameters": {}, "extra": True}),
            command("get_state"),
        ])
        self.assert_error(responses[0], "malformed JSON")
        self.assert_error(responses[1], "malformed JSON")
        for response in responses[2:6]:
            self.assert_error(response, "command must be an object")
        self.assert_error(responses[6], "missing command")
        self.assert_error(responses[7], "command must be a string")
        self.assert_error(responses[8], "parameters must be an object")
        self.assert_error(responses[9], "unknown command: TICK")
        self.assert_error(responses[10], "unknown command: frob")
        self.assert_ok(responses[11], pair(0, idle(0)))
        self.assert_ok(responses[12], pair(0, idle(0)))
        self.assert_ok(responses[13], pair(0, idle(0)))

    def test_missing_command_fields(self):
        responses = self.run_lines([
            init_command(),
            json.dumps({"command": "set_destination", "parameters": {"destination": 1}}),
            json.dumps({"command": "set_destination", "parameters": {"vessel_id": 1, "destination": 1}}),
            json.dumps({"command": "set_destination", "parameters": {"vessel_id": "v1"}}),
            json.dumps({"command": "dock", "parameters": {}}),
            json.dumps({"command": "load", "parameters": {"vessel_id": "v1"}}),
            json.dumps({"command": "swap", "parameters": {"vessel_id": "v1", "unload_destination": 1}}),
            json.dumps({"command": "get_state_at", "parameters": {"tick": "0"}}),
            json.dumps({"command": "get_state_at", "parameters": {}}),
            command("get_state"),
        ])
        self.assert_error(responses[1], "missing vessel_id")
        self.assert_error(responses[2], "vessel_id must be a string")
        self.assert_error(responses[3], "missing destination")
        self.assert_error(responses[4], "missing vessel_id")
        self.assert_error(responses[5], "missing destination")
        self.assert_error(responses[6], "missing load_destination")
        self.assert_error(responses[7], "expected integer")
        self.assert_error(responses[8], "missing tick")
        self.assert_ok(responses[9], pair(0, idle(0)))

    def test_crlf_and_trailing_data(self):
        payload = (
            init_command() + "\r\n" +
            command("get_state") + "\r\n" +
            command("get_state") + command("tick") + "\n"
        )
        completed = subprocess.run(
            [simulator_path()],
            input=payload,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 3)
        parsed = [json.loads(line) for line in lines]
        self.assert_ok(parsed[0], pair(0, idle(0)))
        self.assert_ok(parsed[1], pair(0, idle(0)))
        self.assert_error(parsed[2], "malformed JSON")

    def test_empty_stdin_produces_no_output(self):
        completed = subprocess.run(
            [simulator_path()],
            input="",
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")

    def test_last_line_without_newline(self):
        completed = subprocess.run(
            [simulator_path()],
            input=init_command(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        lines = completed.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assert_ok(json.loads(lines[0]), pair(0, idle(0)))

    def test_pdf_cargo_and_history_example(self):
        example = (ROOT / "examples" / "cargo_delivery.jsonl").read_text(encoding="utf-8")
        lines = [line for line in example.splitlines() if line]
        responses = self.run_lines(lines)
        carried = [lot(2), lot(1)]
        delivered = [lot(1)]
        arrived = [dock_lot(0, 2, 1), dock_lot(0, 1, 1)]

        self.assert_ok(responses[0], pair(0, idle(0)))
        self.assert_ok(responses[1], pair(1, idle(0), arrived))
        self.assert_ok(responses[2], pair(1, docked(0), arrived))
        self.assert_ok(responses[3], pair(2, docked(0), arrived))
        self.assert_ok(responses[4], pair(2, docked(0, [lot(2)]), [dock_lot(0, 1, 1)]))
        self.assert_ok(responses[5], pair(2, docked(0, carried)))
        self.assert_ok(responses[6], pair(3, docked(0, carried)))
        self.assert_ok(responses[7], pair(3, idle(0, carried)))
        self.assert_ok(responses[8], pair(4, idle(0, carried)))
        self.assert_ok(responses[9], pair(4, transit(0, 2, 11, carried)))
        for offset, tick in enumerate(range(5, 11), start=10):
            self.assert_ok(responses[offset], pair(tick, transit(0, 2, 11, carried)))
        self.assert_ok(responses[16], pair(11, idle(2, carried)))
        self.assert_ok(responses[17], pair(11, docked(2, carried)))
        self.assert_ok(responses[18], pair(12, docked(2, carried)))
        self.assert_ok(responses[19], pair(12, docked(2, delivered)))
        self.assert_ok(responses[20], pair(13, docked(2, delivered)))
        self.assert_ok(responses[21], pair(1, idle(0), arrived))
        self.assert_ok(responses[22], pair(13, docked(2, delivered)))
        self.assert_error(responses[23], "tick 99 is in the future (current tick: 13)")
        self.assert_ok(responses[24], pair(13, docked(2, delivered)))

    def test_stdout_has_one_json_object_per_line(self):
        lines = [
            "not json",
            init_command(),
            command("dock", vessel_id="v1"),
            command("load", vessel_id="v1", destination=1),
        ]
        responses = self.run_lines(lines)
        self.assertEqual([response["status"] for response in responses], [
            "error",
            "ok",
            "ok",
            "error",
        ])
        self.assert_error(responses[0], "malformed JSON")
        self.assert_error(responses[3], "vessel v1 is not docked")


if __name__ == "__main__":
    unittest.main()
