# FVM and FEM Discretization

## Finite Volume Method (FVM)

FVM integrates the governing PDE over a control volume and enforces conservation:

```
∫_V ∂φ/∂t dV + ∮_S F(φ)·n̂ dS = ∫_V Q dV
```

### Cell-centered FVM skeleton

```python
# Divergence operator: sum face fluxes over cell faces
def divergence(phi, mesh):
    div = np.zeros(mesh.n_cells)
    for face in mesh.faces:
        flux = face.area * face.normal @ interpolate_face(phi, face)
        div[face.owner] += flux
        div[face.neighbour] -= flux
    return div
```

### Gradient reconstruction (Green-Gauss)

```python
def grad_green_gauss(phi, mesh):
    grad = np.zeros((mesh.n_cells, 3))
    for face in mesh.faces:
        phi_f = 0.5 * (phi[face.owner] + phi[face.neighbour])
        grad[face.owner]    += phi_f * face.area * face.normal
        grad[face.neighbour] -= phi_f * face.area * face.normal
    return grad / mesh.cell_volumes[:, None]
```

## Finite Element Method (FEM)

FEM seeks a weak solution by testing against basis functions:

```
a(u, v) = L(v)  for all v in test space
```

### Assembly pattern

```python
# Stiffness matrix K_ij = ∫ ∇φ_i · ∇φ_j dΩ
def assemble_stiffness(mesh, material):
    K = lil_matrix((mesh.n_dofs, mesh.n_dofs))
    for elem in mesh.elements:
        Ke = elem_stiffness(elem, material)
        for i, gi in enumerate(elem.global_dofs):
            for j, gj in enumerate(elem.global_dofs):
                K[gi, gj] += Ke[i, j]
    return K.tocsr()
```

### Gauss quadrature (2D quadrilateral, 2×2 rule)

| Point (ξ, η)     | Weight |
|------------------|--------|
| (±1/√3, ±1/√3)  | 1.0    |

```python
XI_PTS = [(-0.577350, -0.577350), (0.577350, -0.577350),
          (-0.577350,  0.577350), (0.577350,  0.577350)]
WEIGHTS = [1.0, 1.0, 1.0, 1.0]
```

## Interpolation Schemes

| Scheme          | Order | Notes                                        |
|-----------------|-------|----------------------------------------------|
| Upwind          | 1st   | Robust, diffusive; use for first iteration  |
| Linear (CDS)    | 2nd   | Unbounded on skewed meshes                  |
| Van Leer (MUSCL)| ~2nd  | TVD limiter; good for convection-dominated  |
| QUICK           | 3rd   | Accurate but conditionally stable           |

## Common Pitfalls

- **Non-orthogonality correction**: skewed meshes require explicit correction term or over-relaxation.
- **Checkerboard pressure**: co-located grids need Rhie-Chow interpolation for pressure-velocity coupling.
- **Mass conservation**: verify discrete divergence = 0 at each timestep.
