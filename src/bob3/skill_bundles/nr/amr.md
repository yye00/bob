# Adaptive Mesh Refinement (AMR) for Binary Black Holes

## Berger-Oliger AMR

Hierarchical level structure; fine grids nested inside coarse grids:

```
Level 0: coarsest (outer boundary ~1000 M)
Level 1: 2× refinement
...
Level L: finest (covers puncture ~0.01 M)

Refinement ratio r: typically 2 (dyadic) or 3
```

### Regridding Criterion

```python
def needs_refinement(cell, fields, truncation_error_threshold):
    """Richardson extrapolation to estimate local truncation error."""
    error = richardson_error(cell, fields)
    return error > truncation_error_threshold

def richardson_error(cell, fields):
    """Two-level difference as truncation error proxy."""
    f_h  = interpolate(fields['fine'],   cell)
    f_2h = interpolate(fields['coarse'], cell)
    return abs(f_h - f_2h) / (2**order - 1)
```

### Time Stepping (Berger-Colella)

Fine levels take multiple small steps to stay synchronized:

```
Level L uses dt_L = dt_0 / r^L

for each coarse step:
    advance L=0 by dt_0
    for each fine level (from coarse to fine):
        advance L+1 by r sub-steps of dt_{L+1}
        synchronize: restrict fine → coarse (average down)
        prolongate: coarse → fine ghost zones
```

## Refinement Around Punctures (Moving Box Method)

Track puncture location and follow it:

```python
class PunctureTracker:
    def __init__(self, x0, v0):
        self.pos = np.array(x0)
        self.vel = np.array(v0)
    
    def update(self, alpha, beta, dt):
        """Advance puncture position using gauge evolution."""
        # Puncture moves as dx/dt = -β^i / α at puncture location
        self.vel = -interpolate(beta, self.pos) / interpolate(alpha, self.pos)
        self.pos += self.vel * dt
    
    def refinement_center(self):
        return self.pos
```

## Boundary Conditions Between Levels

### Prolongation (coarse → fine ghost zones)

```python
def prolongate(coarse_field, fine_ghost, order=5):
    """Conservative prolongation with 5th-order polynomial interpolation."""
    return polynomial_interpolate(coarse_field, fine_ghost.coords, order)
```

### Restriction (fine → coarse, conservation-preserving)

```python
def restrict(fine_field, coarse_cell):
    """Average fine cells within coarse cell (volume-weighted)."""
    children = get_fine_children(coarse_cell)
    return sum(f.volume * fine_field[f] for f in children) / coarse_cell.volume
```

## AMR Frameworks

| Framework  | Language | Notes                                |
|------------|----------|--------------------------------------|
| Carpet     | C++      | Cactus-based; widely used in NR      |
| AMReX      | C++      | Modern, GPU-capable                  |
| GRChombo   | C++      | Chombo-based; Lagrangian punctures   |
| GR-Hydro   | C++      | Generalized harmonic + AMR           |

## Common Pitfalls

- **Reflections at refinement boundaries**: use buffer zones (≥ 4 ghost cells) and smooth prolongation.
- **Time-step synchronization**: all child levels must complete before parent advances.
- **Constraint violation growth**: monitor H, M^i; AMR can introduce constraint violations at level boundaries.
