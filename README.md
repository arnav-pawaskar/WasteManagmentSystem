# Fog-Based Smart Waste Management System

A distributed fog computing system for optimizing garbage truck routes and managing smart waste collection across multiple zones.

## System Overview

This system demonstrates a complete fog-based architecture with three core modules:

1. **Route Optimization Module** - Computes optimal garbage truck routes using Nearest Neighbour algorithm
2. **Inter-Fog Communication Module** - Enables peer discovery, state gossip, and load balancing between zones
3. **Election Module** - Implements leader election for coordinating cross-zone decisions (placeholder for teammate implementation)

## Architecture

```
Smart Bin Simulator
        |
        v
    Fog Node
        |
        +-- Route Optimization Module
        |   |-- routing.py (Nearest Neighbour algorithm)
        |   |-- priority.py (Bin priority management)
        |   +-- route_manager.py (Route planning and execution)
        |
        +-- Inter-Fog Communication Module
        |   |-- peer_discovery.py (Node discovery)
        |   |-- gossip.py (State sharing)
        |   |-- spillover.py (Load balancing)
        |   +-- messaging.py (Message routing)
        |
        +-- Election Module (Teammate implementation)
        |
        v
Truck Route Output
```

## Features

### Route Optimization
- **Nearest Neighbour Algorithm**: Simple, deterministic route planning
- **Dynamic Replanning**: Automatically recalculate routes when new bins overflow
- **Priority Management**: Bins prioritized by fill level (critical > high > medium > low)
- **Multi-Truck Support**: Distribute bins among multiple trucks per zone

### Inter-Fog Communication
- **Peer Discovery**: Automatic detection of other fog nodes
- **Gossip Protocol**: Share zone state information across the network
- **Load Balancing**: Transfer bins between overloaded and underloaded zones
- **Message Routing**: Reliable message delivery between nodes

### System Integration
- **Distributed Architecture**: Each fog node operates independently
- **Leader Election**: Coordinate cross-zone decisions through elected leader
- **Real-time Processing**: Handle bin overflow events as they occur
- **Scalable Design**: Easy to add more zones and bins

## Quick Start

### Prerequisites
- Python 3.7+
- No external dependencies required (uses only standard library)

### Installation
```bash
git clone <repository-url>
cd fog-waste-system
```

### Running the System

#### Basic Demo (2 minutes)
```bash
python main.py --demo-duration 120
```

#### Interactive Mode
```bash
python main.py --interactive
```
Commands:
- `status` - Print system status
- `stats` - Print detailed statistics  
- `leader <zone>` - Elect new leader
- `quit` - Exit system

#### Custom Configuration
```bash
python main.py --zones 5 --bins-per-zone 20 --trucks-per-zone 2 --update-interval 3
```

#### Scenario Demo
```bash
python demo.py --scenario high-load
```

### Running Tests
```bash
# Route optimization tests
python tests/test_route_optimization.py

# Inter-fog communication tests
python tests/test_inter_fog_comm.py
```

## Project Structure

```
fog-waste-system/
|
|-- modules/
|   |-- route_optimizer/
|   |   |-- __init__.py
|   |   |-- routing.py          # Route optimization algorithm
|   |   |-- priority.py         # Bin priority management
|   |   +-- route_manager.py    # Route planning and execution
|   |
|   |-- inter_fog_comm/
|   |   |-- __init__.py
|   |   |-- peer_discovery.py   # Node discovery
|   |   |-- gossip.py          # State sharing protocol
|   |   |-- spillover.py       # Load balancing
|   |   +-- messaging.py       # Message routing
|   |
|   +-- election_module/       # Teammate implementation
|
|-- simulation/
|   |-- bin_simulator.py       # Synthetic bin data generation
|   +-- fog_node_simulator.py  # Multi-node simulation
|
|-- contracts/
|   +-- message_types.py       # Shared data structures
|
|-- tests/
|   |-- test_route_optimization.py
|   +-- test_inter_fog_comm.py
|
|-- main.py                     # System entry point
|-- demo.py                     # Demo scenarios
+-- README.md                   # This file
```

## Core Data Structures

### BinTelemetry
```python
@dataclass
class BinTelemetry:
    bin_id: str
    zone_id: int
    x: float
    y: float
    fill_level: float
    timestamp: datetime
```

### ZoneState
```python
@dataclass
class ZoneState:
    zone_id: int
    active_bins: int
    truck_count: int
    timestamp: datetime
```

### RoutePlan
```python
@dataclass
class RoutePlan:
    truck_id: str
    zone_id: int
    route_bins: List[str]
    route_distance: float
```

## Algorithm Details

### Route Optimization (Nearest Neighbour)
1. Start from truck position
2. Find nearest unvisited overflowing bin
3. Add bin to route
4. Update truck position
5. Repeat until all bins visited

### Load Balancing (Spillover)
1. Detect zone overload (active_bins > threshold)
2. Find least-loaded peer zone
3. Send spillover request
4. Peer accepts/rejects based on current load
5. Transfer bin responsibility if accepted

### Peer Discovery
1. Periodic presence broadcasts
2. Heartbeat monitoring
3. Automatic peer registration
4. Timeout-based peer removal

## Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `zones` | 3 | Number of fog zones |
| `bins_per_zone` | 15 | Smart bins per zone |
| `trucks_per_zone` | 1 | Garbage trucks per zone |
| `update_interval` | 5 | Bin fill update interval (seconds) |
| `overload_threshold` | 10 | Zone overload threshold (bins) |
| `overflow_threshold` | 80 | Bin overflow threshold (fill %) |

## System Behavior

### Normal Operation
1. Bins gradually fill with stochastic growth (1-5% per update)
2. Overflowing bins trigger route planning
3. Trucks service bins along optimized routes
4. Zone state shared with peers via gossip

### Load Balancing
1. Overloaded zones initiate spillover
2. Underloaded zones receive bin transfers
3. Leader resolves conflicts if needed
4. System maintains load equilibrium

### Leader Coordination
1. One zone elected as leader
2. Leader handles cross-zone conflicts
3. Followers perform local operations
4. System stability maintained

## Demo Output Examples

### Route Generation
```
Zone 1: Generated 1 routes
  Truck truck_1_1: 3 bins, 45.2 units
```

### Spillover Events
```
Zone 1: Initiating spillover to Zone 2 - 2 bins
[SPILLOVER] Zone 1 requesting help from Zone 2
[SPILLOVER] Zone 2 ACCEPTED request from Zone 1
```

### System Status
```
System Totals:
  Total Bins: 45
  Total Overflowing: 8
  Total Routes Completed: 12
  Total Bins Serviced: 28
  Total Spillovers: 3
```

## Testing

The system includes comprehensive unit tests for all modules:

- **Route Optimization Tests**
  - Distance calculations
  - Route planning algorithms
  - Priority management
  - Route validation

- **Inter-Fog Communication Tests**
  - Peer discovery
  - Gossip protocol
  - Spillover management
  - Message routing

Run tests with:
```bash
python -m unittest discover tests/
```

## Future Enhancements

### Route Optimization
- Implement advanced algorithms (TSP, genetic algorithms)
- Consider traffic patterns and road networks
- Add real-time truck tracking
- Optimize for fuel efficiency

### Communication
- Implement secure messaging
- Add network topology awareness
- Implement consensus protocols
- Add fault tolerance mechanisms

### Election Module
- Complete invitation election algorithm
- Add leader health monitoring
- Implement automatic failover
- Add election conflict resolution

## Performance Considerations

- **Scalability**: System scales linearly with zones and bins
- **Latency**: Message delivery simulated with 1-2 second delays
- **Memory**: Efficient data structures for large deployments
- **CPU**: Optimized algorithms for real-time processing

## Troubleshooting

### Common Issues

1. **No routes generated**: Check if bins are overflowing (fill_level >= 80%)
2. **Spillover not working**: Verify peer discovery and network connectivity
3. **High memory usage**: Reduce number of bins or increase cleanup intervals
4. **Slow performance**: Adjust update intervals or optimize algorithms

### Debug Mode
Enable detailed logging by modifying the update_interval parameter:
```bash
python main.py --update-interval 1  # More frequent updates for debugging
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit pull request

## License

This project is for educational purposes. Feel free to use and modify as needed.

---

**Note**: The Election Module is designed for teammate implementation. The current system includes placeholder interfaces and demonstrates integration patterns for the complete system.
