# Fault Slip: Coulomb and Rate-and-State Friction

## Coulomb Failure Criterion

Static failure condition:

```
τ_f = c + μ_s (σ_n - p)

τ_f : failure shear stress
c   : cohesion [Pa]
μ_s : static friction coefficient
σ_n : normal stress (positive compressive)
p   : pore pressure [Pa]

Coulomb Failure Function: CFF = τ - τ_f
  CFF > 0 → failure (slip)
  CFF ≤ 0 → locked
```

## Rate-and-State Friction (Dieterich-Ruina)

Steady-state friction depends on slip velocity V and state variable θ:

```
μ = μ_0 + a·ln(V/V_0) + b·ln(θ V_0/D_c)

State evolution (aging law):
dθ/dt = 1 - V θ / D_c

Parameters:
  a : direct velocity effect (positive)
  b : state evolution effect (positive)
  D_c : critical slip distance [m]
  V_0 : reference velocity [m/s]
```

### Velocity-weakening (seismogenic): a - b < 0

```python
a, b, D_c = 0.008, 0.012, 1e-5   # typical seismogenic values
# Slip weakens friction → instability (earthquake nucleation)
```

### Velocity-strengthening (stable creep): a - b > 0

```python
a, b, D_c = 0.015, 0.010, 1e-5   # upper/lower crustal transition
# Slip strengthens friction → stable sliding
```

## Spring-Slider Model (Nucleation)

```python
def rate_state_ode(t, state, k, V_lp, a, b, D_c, sigma_n, mu_0, V_0):
    V, theta = state
    mu = mu_0 + a*np.log(V/V_0) + b*np.log(theta*V_0/D_c)
    dV_dt = (k*(V_lp - V) - b*sigma_n*V/D_c * (1 - theta*V/D_c)) / (a*sigma_n/V)
    dtheta_dt = 1.0 - V*theta/D_c
    return [dV_dt, dtheta_dt]
```

## Stress Transfer (Coulomb Stress Change)

```python
def coulomb_stress_change(delta_tau, delta_sigma_n, mu_s, delta_p=0):
    """Stress change on a receiver fault from a finite source."""
    return delta_tau + mu_s * (delta_sigma_n - delta_p)
```

## Common Pitfalls

- **Stiff ODE**: rate-and-state ODEs become very stiff near instability; use adaptive Runge-Kutta (e.g., LSODA or Radau).
- **Grid resolution**: spatial nucleation requires Δx < h_c = G D_c / (π (b-a) σ_n).
- **Radiation damping**: add η V term to quasi-dynamic formulation to limit slip velocity.
