# Turbulence Models

## RANS Models

### k-ε (Standard)

Transport equations for turbulent kinetic energy k and dissipation ε:

```
Dk/Dt  = ∇·[(ν + νt/σ_k) ∇k]  + P_k - ε
Dε/Dt  = ∇·[(ν + νt/σ_ε) ∇ε]  + C1ε (ε/k) P_k - C2ε ε²/k

νt = Cμ k²/ε

Standard constants: Cμ=0.09, C1ε=1.44, C2ε=1.92, σ_k=1.0, σ_ε=1.3
```

**When to use**: industrial flows, far from wall; poor in adverse pressure gradient.

### k-ω SST (Shear-Stress Transport, Menter 1994)

Blends k-ω near wall (better in adverse pressure gradient) with k-ε in freestream:

```python
F1 = tanh(arg1**4)          # blending function: 1 near wall, 0 freestream
omega_eq = F1*omega_kw + (1-F1)*omega_ke
nu_t = a1*k / max(a1*omega, S*F2)   # stress-limiter prevents over-prediction
```

**Constants**: β*=0.09, κ=0.41, a1=0.31.

### Spalart-Allmaras (SA)

Single transport equation for modified eddy viscosity ν̃:

```
Dν̃/Dt = Cb1 S̃ ν̃ + (1/σ) ∇·[(ν+ν̃) ∇ν̃] + Cb2 |∇ν̃|² - Cw1 fw (ν̃/d)²
```

Good for external aerodynamics; simple and robust.

## LES (Large Eddy Simulation)

Resolves large scales; models only sub-grid scales (SGS):

```
Filtered NS:   ∂ũ/∂t + ũ·∇ũ = -∇p̃/ρ + ν∇²ũ - ∇·τ_SGS

Smagorinsky SGS:  τ_SGS = -2(Cs Δ)² |S̃| S̃
Cs ≈ 0.1–0.2 (problem-dependent)
```

**Requirements**: fine mesh (Δ+ ~ 1 near wall for wall-resolved LES); expensive.

## Wall Treatment

| y⁺ range | Approach              |
|----------|-----------------------|
| y⁺ < 1   | Low-Re model, resolve sublayer |
| 30–300   | Standard wall function (log law) |
| 5–30     | Enhanced wall treatment (blended) |

```python
u_tau = sqrt(nu * du/dy_wall)
y_plus = y_wall * u_tau / nu
u_plus = (1/kappa) * log(E * y_plus)  # kappa=0.41, E=9.8
```

## Common Pitfalls

- **k-ε with adverse pressure gradient**: use k-ω SST instead.
- **Over-production in stagnation**: apply production limiters (P_k ≤ 10ε).
- **LES on coarse mesh**: check resolved TKE fraction (should be > 80%).
