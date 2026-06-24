# Gauge Conditions in Numerical Relativity

## 1+log Slicing (Bona-Massó)

Singularity-avoiding slicing for the lapse α:

```
∂_t α = -2 α K + β^i ∂_i α

Characteristic speed: 0 (non-advecting form)
Advecting form: ∂_t α = β^i ∂_i α - 2 α K
```

Properties:
- Collapses to harmonic slicing (α = 1) for K = 0.
- Avoids coordinate singularities ("freezing" at horizon).
- Combined with moving punctures: very robust for BBH.

## Gamma-Driver Shift (Campanelli et al. 2006)

Dynamically drives shift to reduce coordinate distortions:

```
∂_t β^i = (3/4) B^i + β^j ∂_j β^i

∂_t B^i = ∂_t Γ̃^i - η B^i + β^j ∂_j B^i

η : damping parameter (typically η ~ 2/M, M = total ADM mass)
```

The B^i auxiliary variable prevents oscillations.

```python
# Recommended initial data
alpha_0 = 1.0                         # initially flat lapse
beta_0  = np.zeros(3)                 # no initial shift
B_0     = np.zeros(3)                 # no initial B

# After merger, alpha collapses near horizon: alpha ~ 0.3
```

## Moving Puncture Gauge (Standard BBH Recipe)

Combined gauge choice that has become the community standard:

```python
# Lapse: 1+log
dtAlpha = -2.0 * alpha * K + beta_i * d_i_alpha

# Shift: Gamma-driver  
dtBeta_i = 0.75 * B_i
dtB_i    = dtGamma_i - eta * B_i

# Numerical parameters
eta  = 2.0 / M_ADM    # M_ADM = total mass in geometric units
```

## Static Trumpet Punctures

Initial data with 1+log/Gamma-driver admits "trumpet" geometry at puncture:

- Singularity excised naturally (never reached in coordinate time).
- Avoids "grid stretching" of older excision methods.

## Harmonic / Generalized Harmonic

Alternative gauge (used by SpEC/GR-Hydro):

```
□ x^μ = H^μ(x, g)

∂_t α_harmonic = β^i ∂_i α - α² (K - K0)
```

## Common Pitfalls

- **η too large**: over-damps shift → coordinate drift.
- **η too small**: shift oscillations → crashes.
- **Lapse sign flip**: if α < 0, code will diverge; add max(α, 1e-6) floor.
- **Initial transient**: "junk radiation" in first few M; discard in analysis.
