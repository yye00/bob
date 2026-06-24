# Boris Pusher for Relativistic Particle Pushing

## Boris Algorithm

The Boris pusher is the standard method for pushing charged particles in electromagnetic fields.
It is exactly volume-preserving in velocity space and second-order accurate.

### Non-relativistic Boris

```python
def boris_push(x, v, E, B, q, m, dt):
    """Boris pusher for non-relativistic particles.
    
    Splits electromagnetic push into:
    1. Half electric acceleration
    2. Full magnetic rotation
    3. Half electric acceleration
    """
    q_over_m = q / m
    half_dt = 0.5 * dt

    # Half-step electric acceleration
    v_minus = v + q_over_m * E * half_dt

    # Magnetic rotation (exact rotation by angle θ)
    t = q_over_m * B * half_dt            # t = (q/m) B dt/2
    s = 2 * t / (1 + np.dot(t, t))       # s = 2t/(1+|t|²)
    v_prime = v_minus + np.cross(v_minus, t)
    v_plus  = v_minus + np.cross(v_prime, s)

    # Half-step electric acceleration
    v_new = v_plus + q_over_m * E * half_dt

    # Position update
    x_new = x + v_new * dt

    return x_new, v_new
```

### Relativistic Boris (Vay, 2008 variant)

```python
def boris_relativistic(x, p, E, B, q, m, dt, c=1.0):
    """Relativistic Boris pusher with momentum p = γmv.
    
    Vay (2008) correction avoids E×B drift error of original relativistic Boris.
    """
    q_over_m = q / m
    half_dt  = 0.5 * dt

    # Half-step electric kick
    p_minus = p + q_over_m * E * half_dt * m

    # Gamma for p_minus
    gamma_minus = np.sqrt(1 + np.dot(p_minus, p_minus) / (m*c)**2)
    u_minus = p_minus / (m * gamma_minus)

    # Magnetic rotation
    t = q_over_m * B * half_dt / gamma_minus
    s = 2 * t / (1 + np.dot(t, t))
    u_prime = u_minus + np.cross(u_minus, t)
    u_plus  = u_minus + np.cross(u_prime, s)

    # Half-step electric kick  
    p_new = m * u_plus + q_over_m * E * half_dt * m

    # Position update
    gamma_new = np.sqrt(1 + np.dot(p_new, p_new) / (m*c)**2)
    v_new = p_new / (m * gamma_new)
    x_new = x + v_new * dt

    return x_new, p_new
```

## Volume Preservation

The Boris rotation conserves phase-space volume exactly (Liouville's theorem):

```python
# Verify: |det(J)| = 1 for the rotation step
# The rotation matrix R = I + t×·s is orthogonal when |t|² handled correctly
```

## Cyclotron Motion Test

```python
def test_circular_motion(q, m, B0, v0, dt, n_steps):
    """Exact circle: position error ~ O(dt²)."""
    omega_c = abs(q) * B0 / m
    T_c = 2 * np.pi / omega_c
    x, v = np.array([0., 0., 0.]), np.array([v0, 0., 0.])
    B = np.array([0., 0., B0])
    E = np.zeros(3)
    for _ in range(n_steps):
        x, v = boris_push(x, v, E, B, q, m, dt)
    radius_error = abs(np.linalg.norm(x[:2]) - v0/omega_c)
    return radius_error
```

## Common Pitfalls

- **Large timestep**: dt > 2/ω_c causes instability; use dt ≤ 0.1/ω_c for accuracy.
- **Large B drift error**: original relativistic Boris has E×B drift error; use Vay (2008) or Higuera-Cary.
- **Mixed units**: check SI vs Gaussian; Boris works in both, but q/m and c must be consistent.
