# Field Gather and Scatter in PIC Codes

## Gather: Grid Fields → Particle Positions

Interpolate grid-defined fields E, B to particle positions:

```python
def gather_field_1d(field, x, dx, order=1):
    """Gather 1D field to particle position x using B-spline of given order."""
    i = int(x / dx)
    if order == 0:     # Nearest Grid Point (NGP)
        return field[i]
    elif order == 1:   # Cloud-in-Cell (CIC)
        wx = x/dx - i
        return (1 - wx) * field[i] + wx * field[i+1]
    elif order == 2:   # Triangular Shape Cloud (TSC)
        # 3-point stencil centered at i+0.5
        il = i - 1
        wx_l = 0.5*(1.5 - (x/dx - il))**2
        wx_c = 0.75 - (x/dx - i - 0.5)**2
        wx_r = 1 - wx_l - wx_c
        return wx_l*field[il] + wx_c*field[i] + wx_r*field[i+1]
```

## Scatter: Particle Sources → Grid

Current deposition for charge conservation (Esirkepov scheme):

```python
def esirkepov_current(x_old, x_new, q, dx, dt):
    """Charge-conserving current deposition (Esirkepov 2001).
    
    Guarantees ∂ρ/∂t + ∇·J = 0 discretely.
    """
    # Compute shape function differences
    W_old = shape_function(x_old, dx)
    W_new = shape_function(x_new, dx)
    delta_W = W_new - W_old

    # Cumulative sum for current
    J = np.zeros_like(W_old)
    J[0] = -q/dt * delta_W[0]
    for k in range(1, len(delta_W)):
        J[k] = J[k-1] - q/dt * delta_W[k]
    return J
```

## Staggered Yee Grid

Electric and magnetic fields on staggered positions:

```
E_x at (i+½, j, k)       B_x at (i, j+½, k+½)
E_y at (i, j+½, k)       B_y at (i+½, j, k+½)
E_z at (i, j, k+½)       B_z at (i+½, j+½, k)
```

```python
def gather_E_yee(Ex_grid, Ey_grid, Ez_grid, x, y, z, dx, dy, dz):
    """Gather E from staggered Yee grid (E_x at half-integer x)."""
    Ex = interpolate_at(Ex_grid, x - 0.5*dx, y, z, dx, dy, dz)
    Ey = interpolate_at(Ey_grid, x, y - 0.5*dy, z, dx, dy, dz)
    Ez = interpolate_at(Ez_grid, x, y, z - 0.5*dz, dx, dy, dz)
    return np.array([Ex, Ey, Ez])
```

## FDTD Maxwell Solver (Yee)

```python
def yee_advance_E(E, B, J, dx, dt, epsilon_0=1.0):
    """Advance E by one timestep: ∂E/∂t = c²∇×B - J/ε₀"""
    curl_B = curl(B, dx)
    E_new = E + dt * (curl_B - J / epsilon_0)
    return E_new

def yee_advance_B(E, B, dx, dt):
    """Advance B by one timestep: ∂B/∂t = -∇×E"""
    curl_E = curl(E, dx)
    B_new = B - dt * curl_E
    return B_new
```

## Common Pitfalls

- **Non-charge-conserving current**: use Esirkepov or Villasenor-Buneman; simpler schemes violate ∇·E = ρ/ε₀.
- **Staggered gather**: gather E/B at their respective half-integer positions, not cell center.
- **Anti-aliasing**: apply spectral filter (low-pass) after deposition to reduce grid noise.
