# Plasticity: Drucker-Prager and Mohr-Coulomb

## Stress Decomposition

```
σ = p I + s           (pressure + deviatoric)
p = σ_kk / 3         (hydrostatic pressure, positive in compression)
J2 = ½ s:s           (second invariant of deviatoric stress)
q = √(3 J2)          (von Mises equivalent stress)
```

## Mohr-Coulomb Criterion

Failure when shear stress on any plane exceeds:

```
τ_f = c cos φ - σ tan φ     (σ = normal stress, positive tension)

In principal stress space:
f_MC = σ1 - σ3 N_φ - 2c √N_φ  ≤ 0
N_φ = (1 + sin φ) / (1 - sin φ)
```

**Non-smooth corners** at tension and compression meridians require special treatment (e.g., Koiter's corner).

## Drucker-Prager Criterion (Smooth Approximation)

```
f_DP = α_DP p + q - k_DP ≤ 0

Matching MC outer cone (compression meridian):
α_DP = 6 sin φ / (√3 (3 - sin φ))
k_DP = 6 c cos φ / (√3 (3 - sin φ))

Matching MC inner cone (tension meridian):
α_DP = 6 sin φ / (√3 (3 + sin φ))
k_DP = 6 c cos φ / (√3 (3 + sin φ))
```

## Return Mapping Algorithm (Elastic-Plastic Integration)

```python
def return_mapping_dp(sigma_trial, alpha_dp, k_dp, G, K):
    p_tr = trace(sigma_trial) / 3
    s_tr = sigma_trial - p_tr * I
    q_tr = sqrt(3/2) * norm(s_tr)

    f_tr = alpha_dp * p_tr + q_tr - k_dp
    if f_tr <= 0:
        return sigma_trial, 0.0   # elastic

    # Return to smooth yield surface (cone)
    # Solve: Δγ from f(σ(Δγ)) = 0
    denom = 3*G + 9*K*alpha_dp**2
    delta_gamma = f_tr / denom
    p = p_tr - 9*K*alpha_dp * delta_gamma
    s = s_tr * (1 - 3*G*delta_gamma/q_tr)
    return p*I + s, delta_gamma
```

## Hardening Laws

### Isotropic hardening

```
k(κ) = k_0 + H κ    (linear)     H > 0: hardening; H < 0: softening
κ̇ = |ε̇^p| / √(2/3)  (accumulated plastic strain)
```

### Softening (Localization)

Requires regularization (non-local, gradient-enhanced, or mesh-size scaling):

```python
# Mesh-size regularization (Bažant)
G_f = fracture_energy   # [J/m²]
h   = element_size
H_local = -G_f * sigma_peak / h   # softening modulus per element size
```

## Common Pitfalls

- **MC corners**: use smoothed Mohr-Coulomb or check corner algorithm separately.
- **Softening without regularization**: pathological mesh dependence; localization width = 0.
- **Consistent tangent**: use algorithmic (consistent) tangent for quadratic convergence of Newton.
