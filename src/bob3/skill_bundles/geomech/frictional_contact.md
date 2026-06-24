# Frictional Contact Mechanics

## Kuhn-Tucker Contact Conditions

For a contact pair with gap g_N and contact pressure p_N:

```
g_N ≥ 0,   p_N ≤ 0,   g_N · p_N = 0   (normal, non-penetration)
|t_T| ≤ μ|p_N|                          (Coulomb friction cone)
```

## Penalty Method

Weakly enforces non-penetration via penalty stiffness ε_N:

```python
f_contact = -epsilon_N * min(g_N, 0)  # normal penalty force
# Tangential (stick-slip)
if |t_T_trial| <= mu * |f_N|:
    t_T = t_T_trial          # stick
else:
    t_T = mu * |f_N| * t_T_trial / |t_T_trial|  # slip
```

**Limitation**: exact constraint satisfaction requires ε_N → ∞ (ill-conditioning).

## Augmented Lagrangian (Simo-Laursen)

Combines Lagrange multiplier accuracy with penalty robustness:

```
L̄(u, λ, ε_N) = Π(u) + ∫_Γc [λ g_N + ε_N/2 g_N²] dΓ

Update rule (Uzawa):
λ_{k+1} = min(λ_k + ε_N g_N, 0)   # projection onto admissible cone
```

Converges to exact constraint with finite ε_N; outer loop needed.

## Mortar Method (Variationally Consistent)

```python
# Integrate contact forces with dual Lagrange multipliers
# slave side: psi_i (dual basis, biorthogonal to phi_i)
# master side: phi_j (standard Lagrange basis)
D_ij = ∫ psi_i phi_j dΓ   # mortar coupling matrix
```

Advantages: passes patch test; handles non-conforming meshes.

## Active-Set Strategy

```python
active_set = set()
for iteration in range(max_iter):
    solve_linear_system(active_set)
    # Check constraints
    new_active = {node for node in candidates if gap(node) < 0}
    if new_active == active_set:
        break
    active_set = new_active
```

## Friction States

| State  | Condition             | Slip increment |
|--------|-----------------------|----------------|
| Stick  | Δs = 0                | No sliding     |
| Slip   | |t_T| = μ|p_N|       | Δs = Δs_slip   |
| Open   | g_N > 0, p_N = 0     | —              |

## Common Pitfalls

- **Chattering**: contact state oscillates → use consistent linearization or damping.
- **Penalty too small**: penetration not prevented → increase ε_N, but monitor condition number.
- **Asymmetric tangent**: ensure consistent contact tangent for Newton convergence.
