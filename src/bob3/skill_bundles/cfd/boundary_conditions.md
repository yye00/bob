# CFD Boundary Conditions

## Inlet Conditions

### Velocity inlet

```python
# Dirichlet for velocity, zero-gradient for pressure
bc_inlet = {
    "U":   "fixedValue",    # specify U profile
    "p":   "zeroGradient",
    "k":   "fixedValue",    # k = 1.5 (I*U_ref)²
    "epsilon": "fixedValue", # ε = Cμ^0.75 k^1.5 / L
}
```

### Pressure inlet (total pressure known)

```python
bc_pressure_inlet = {
    "U": "pressureInletVelocity",  # derived from p_total
    "p": "totalPressure",          # p_total = p + 0.5ρU²
}
```

## Outlet Conditions

### Pressure outlet (outflow)

```python
bc_outlet = {
    "U": "zeroGradient",   # fully-developed flow assumption
    "p": "fixedValue",     # gauge pressure = 0
}
```

### Backflow prevention

```python
# Use inletOutlet for k, ω at pressure outlets
bc_k_outlet = {
    "type": "inletOutlet",
    "inletValue": k_freestream,
    "value": k_freestream,
}
```

## Wall Conditions

```python
bc_wall = {
    "U": "noSlip",           # u = 0 (non-moving wall)
    "p": "zeroGradient",
    "k": "kqRWallFunction",
    "epsilon": "epsilonWallFunction",
    "omega":   "omegaWallFunction",
    "nut":     "nutkWallFunction",
}

# Moving wall (e.g., rotating fan)
bc_moving_wall = {
    "U": "movingWallVelocity",
    "type": "rotatingWallVelocity",
    "axis":   [0, 0, 1],
    "omega":  100.0,  # rad/s
}
```

## Symmetry

```python
bc_symmetry = {
    "U": "symmetry",       # normal component = 0, tangential zero-gradient
    "p": "symmetry",
}
```

## Periodic / Cyclic

```python
# Pair two boundary patches; enforce φ_master = φ_slave
bc_periodic = {
    "type": "cyclic",
    "matchTolerance": 1e-4,
}
```

## Far-field (Compressible)

```python
# Riemann-based far-field; uses characteristic variables
bc_farfield = {
    "type": "characteristicFarField",
    "Mach": 0.3,
    "alpha": 2.0,   # angle of attack [deg]
    "p_inf": 101325.0,
    "T_inf": 288.15,
}
```

## Common Pitfalls

- **Inlet turbulence intensity too low**: leads to laminar-like RANS; use I = 0.05 as minimum.
- **Outlet reflections in compressible flow**: non-reflective BC required for acoustics.
- **Symmetry vs periodic**: use periodic only when the flow is truly periodic, not just geometrically symmetric.
