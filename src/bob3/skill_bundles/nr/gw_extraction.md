# Gravitational Wave Extraction

## Newman-Penrose Scalar Ψ₄

GWs encoded in the Newman-Penrose scalar at null infinity (scri⁺):

```
Ψ₄ = C_{αβγδ} n^α m̄^β n^γ m̄^δ

n^μ: outgoing null vector
m^μ: complex null vector in transverse plane

Ψ₄ = ḧ₊ - i ḧˣ  (dominant approximation, large r)
```

Relates to strain:
```
h₊ - i hˣ = -∫∫ Ψ₄ dt² dt
```

## Tetrad Construction (Pseudo-Kinnersley)

```python
def pseudo_kinnersley_tetrad(gamma_ij, beta_i, alpha, radius):
    """Construct null tetrad adapted to radial direction."""
    r_hat = unit_radial_vector(radius)
    # Quasi-kinnersley frame
    n_mu  = (1/(alpha*sqrt(2))) * np.array([1, -(alpha*r_hat + beta_i)])
    l_mu  = (1/(alpha*sqrt(2))) * np.array([1,  (alpha*r_hat - beta_i)])
    m_mu  = complex_null_vector_transverse(gamma_ij, r_hat)
    return l_mu, n_mu, m_mu
```

## Spin-Weighted Spherical Harmonics Decomposition

Expand Ψ₄ on extraction sphere of radius r_ex:

```python
def extract_modes(Psi4, theta, phi, ell_max=8):
    """Decompose Psi4 into spin-weight -2 spherical harmonic modes."""
    modes = {}
    for ell in range(2, ell_max+1):
        for m in range(-ell, ell+1):
            Y_lm = spin_weighted_sph_harm(-2, ell, m, theta, phi)
            # Integrate over sphere
            modes[(ell, m)] = np.trapz(np.trapz(
                Psi4 * np.conj(Y_lm) * np.sin(theta),
                theta, axis=0), phi, axis=0)
    return modes
```

## Extrapolation to Null Infinity (Scri⁺)

Extract at multiple radii and extrapolate:

```python
def extrapolate_to_scri(psi4_rN, radii, retarded_times, order=3):
    """Extrapolate r*Psi4 as polynomial in 1/r."""
    # For each retarded time u, fit polynomial r*Psi4 = A0 + A1/r + ...
    r_psi4 = [r * psi4 for r, psi4 in zip(radii, psi4_rN)]
    inv_r  = [1.0/r for r in radii]
    coeffs = np.polyfit(inv_r, r_psi4, order)
    return coeffs[-1]   # A0 is the scri+ value
```

## Radiated Energy and Angular Momentum

```python
def radiated_power(psi4_modes, r_ex):
    """Instantaneous GW power dE/dt at extraction radius r."""
    power = r_ex**2 / (16*np.pi) * sum(
        abs(dh_dt)**2  # dh_dt integrated from Psi4
        for (l, m), dh_dt in modes.items()
    )
    return power

def radiated_angular_momentum(psi4_modes, dh_modes, r_ex):
    """dJ/dt from GW modes."""
    dJz_dt = -r_ex**2 / (16*np.pi) * sum(
        m * np.imag(np.conj(dh_modes[(l,m)]) * psi4_modes[(l,m)])
        for (l, m) in modes
    )
    return dJz_dt
```

## Common Pitfalls

- **Double time integration**: cumulative drift in h → use frequency-domain integration with low-frequency cutoff.
- **Near-zone effects**: extract at r_ex > 50M; check r-extrapolation convergence.
- **Mode mixing**: ensure tetrad is properly aligned to avoid (2,2)↔(2,-2) mixing.
