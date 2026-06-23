# Custom Physics Lists in Geant4

## Physics List Architecture

A physics list registers physics processes for each particle type:

```cpp
class MyPhysicsList : public G4VModularPhysicsList {
public:
    MyPhysicsList() {
        SetVerboseLevel(1);
        defaultCutValue = 0.1 * mm;

        // Register modular physics constructors
        RegisterPhysics(new G4EmStandardPhysics());
        RegisterPhysics(new G4HadronPhysicsQGSP_BERT());
        RegisterPhysics(new G4DecayPhysics());
    }
};
```

## Reference Physics Lists

| List                   | Use case                                      |
|------------------------|-----------------------------------------------|
| FTFP_BERT              | HEP default; FTF model + BERT cascade         |
| QGSP_BERT              | Alternative HEP; QGS model                   |
| FTFP_BERT_HP           | Adds high-precision neutron (< 20 MeV)        |
| Shielding              | Neutron transport, medical/nuclear             |
| G4EmStandardPhysics    | EM only (no hadronic)                         |
| G4EmStandardPhysics_option4 | Best EM accuracy (Livermore)             |

## Custom EM Physics Constructor

```cpp
class MyEmPhysics : public G4VPhysicsConstructor {
public:
    void ConstructProcess() override {
        G4PhysicsListHelper* ph = G4PhysicsListHelper::GetPhysicsListHelper();

        auto particleIterator = GetParticleIterator();
        particleIterator->reset();

        while ((*particleIterator)()) {
            G4ParticleDefinition* particle = particleIterator->value();
            G4String pname = particle->GetParticleName();

            if (pname == "e-") {
                ph->RegisterProcess(new G4eMultipleScattering(), particle);
                ph->RegisterProcess(new G4eIonisation(), particle);
                ph->RegisterProcess(new G4eBremsstrahlung(), particle);
            }
            if (pname == "gamma") {
                ph->RegisterProcess(new G4PhotoElectricEffect(), particle);
                ph->RegisterProcess(new G4ComptonScattering(), particle);
                ph->RegisterProcess(new G4GammaConversion(), particle);
            }
        }
    }
};
```

## Production Cuts

```cpp
void MyPhysicsList::SetCuts() {
    SetCutsWithDefault();          // apply defaultCutValue to all

    // Per-region cuts
    G4Region* detRegion = G4RegionStore::GetInstance()->GetRegion("Detector");
    G4ProductionCuts* cuts = new G4ProductionCuts;
    cuts->SetProductionCut(0.01*mm, G4ProductionCuts::GetIndex("gamma"));
    cuts->SetProductionCut(0.01*mm, G4ProductionCuts::GetIndex("e-"));
    detRegion->SetProductionCuts(cuts);
}
```

## Biasing / Variance Reduction

```cpp
// Importance biasing: split particles entering high-importance regions
void MyPhysicsList::ConstructProcess() {
    // ...existing constructors...
    RegisterPhysics(new G4ImportanceBiasing(fImportanceStore, "biasedRegion"));
}

// Wrapper process for forced interaction
class MyForcedDecay : public G4WrapperProcess {
    G4double GetMeanFreePath(const G4Track&, G4double, G4ForceCondition* condition) override {
        *condition = Forced;
        return DBL_MAX;
    }
};
```

## Scoring with G4MultiFunctionalDetector

```cpp
G4MultiFunctionalDetector* det = new G4MultiFunctionalDetector("MyDet");
G4VPrimitiveScorer* scorer = new G4PSEnergyDeposit("eDep");
det->RegisterPrimitive(scorer);
logicalVolume->SetSensitiveDetector(det);
```

## Common Pitfalls

- **Double-counting**: registering a process twice leads to wrong cross-sections; check with `/process/list`.
- **Wrong model range**: BERT cascade valid below ~12 GeV for protons; above that use FTF/QGS.
- **Missing optical physics**: for scintillation/Cherenkov add `G4OpticalPhysics` separately.
- **Thread safety**: physics constructors called once; action initializations called per thread in MT mode.
