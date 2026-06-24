# SIMPLE and PISO Pressure-Velocity Coupling

## SIMPLE Algorithm (Semi-Implicit Method for Pressure-Linked Equations)

Outer iteration loop for steady-state incompressible flow:

```
1. Guess pressure p*
2. Solve momentum equations for u* (using p*)
3. Solve pressure-correction equation for p'
4. Correct pressure:  p = p* + α_p · p'
5. Correct velocity:  u = u* - (1/a_P) ∇p'
6. Repeat until residuals < tolerance
```

### Momentum predictor

```python
def momentum_predictor(u_old, p, mesh, nu, dt):
    # Build A·u = b with under-relaxation α_u
    A, b = assemble_momentum(u_old, p, mesh, nu, dt)
    u_star = spsolve(A, b)
    return u_star
```

### Pressure correction equation

```
∇·(1/a_P ∇p') = ∇·u*
```

```python
def pressure_correction(u_star, a_P, mesh):
    # Laplacian of p' = divergence of u*
    div_u_star = divergence(u_star, mesh)
    L = assemble_laplacian(1.0 / a_P, mesh)
    p_prime = spsolve(L, div_u_star)
    return p_prime
```

### Under-relaxation factors (typical starting values)

| Variable   | α (typical) |
|------------|-------------|
| Velocity   | 0.7         |
| Pressure   | 0.3         |
| Turbulence | 0.5–0.7     |

## PISO Algorithm (Pressure-Implicit with Splitting of Operators)

Transient flow; uses predictor + corrector steps within each timestep:

```
1. Momentum predictor → u*
2. First corrector:   solve p', correct u → u**
3. Second corrector:  solve p'', correct u → u***  (optional)
4. Advance to next timestep
```

PISO requires α_p = 1.0 (no pressure under-relaxation for transient accuracy).

### PIMPLE (OpenFOAM hybrid)

PIMPLE = outer SIMPLE loops + inner PISO correctors. Good for large timesteps (Co > 1).

```python
for outer in range(n_outer):          # SIMPLE outer loops
    solve_momentum()
    for corrector in range(n_correctors):  # PISO correctors
        solve_pressure()
        correct_velocity()
```

## Convergence Monitoring

```python
residuals = {
    "Ux": norm(A_u @ u_x - b_ux) / norm(b_ux),
    "Uy": norm(A_u @ u_y - b_uy) / norm(b_uy),
    "p":  norm(A_p @ p  - b_p)  / norm(b_p),
}
converged = all(r < 1e-5 for r in residuals.values())
```

## Common Pitfalls

- **Divergence**: reduce under-relaxation; refine mesh near high-gradient regions.
- **Pressure–velocity decoupling**: ensure Rhie-Chow interpolation is active.
- **Slow convergence**: check aspect ratio; large aspect ratios slow iterative solvers.
