# Geant4 User Actions

## User Action Architecture

Geant4 uses a callback-based architecture. User inherits from base classes:

```cpp
// Required for simulation control
class MyRunAction    : public G4UserRunAction    { ... };
class MyEventAction  : public G4UserEventAction  { ... };
class MySteppingAction : public G4UserSteppingAction { ... };

// Optional
class MyTrackingAction : public G4UserTrackingAction { ... };
class MyStackingAction : public G4UserStackingAction  { ... };
```

## RunAction

```cpp
class MyRunAction : public G4UserRunAction {
public:
    void BeginOfRunAction(const G4Run* run) override {
        // Initialize histograms, open output files
        fAnalysisManager = G4AnalysisManager::Instance();
        fAnalysisManager->OpenFile("output.root");
        fAnalysisManager->CreateH1("edep", "Energy dep", 100, 0., 10.*MeV);
    }

    void EndOfRunAction(const G4Run* run) override {
        fAnalysisManager->Write();
        fAnalysisManager->CloseFile();
        // Print summary statistics
        G4cout << "Total events: " << run->GetNumberOfEvent() << G4endl;
    }
};
```

## EventAction

```cpp
class MyEventAction : public G4UserEventAction {
    G4double fEdep = 0.;
public:
    void BeginOfEventAction(const G4Event*) override { fEdep = 0.; }

    void EndOfEventAction(const G4Event*) override {
        // Fill histograms with per-event accumulated data
        G4AnalysisManager::Instance()->FillH1(0, fEdep);
    }

    void AddEdep(G4double edep) { fEdep += edep; }
};
```

## SteppingAction

```cpp
class MySteppingAction : public G4UserSteppingAction {
    MyEventAction* fEventAction;
public:
    void UserSteppingAction(const G4Step* step) override {
        // Accumulate energy deposit in sensitive volume
        G4LogicalVolume* volume =
            step->GetPreStepPoint()->GetTouchableHandle()
                ->GetVolume()->GetLogicalVolume();

        if (volume == fDetectorLV) {
            G4double edep = step->GetTotalEnergyDeposit();
            fEventAction->AddEdep(edep);
        }
    }
};
```

## TrackingAction

```cpp
class MyTrackingAction : public G4UserTrackingAction {
public:
    void PreUserTrackingAction(const G4Track* track) override {
        // Called when track is created
        if (track->GetDefinition() == G4Gamma::Gamma()) {
            // Do something for photons
        }
    }

    void PostUserTrackingAction(const G4Track* track) override {
        // Called when track ends; check final kinetic energy, etc.
    }
};
```

## StackingAction (Priority-based Tracking)

```cpp
class MyStackingAction : public G4UserStackingAction {
public:
    G4ClassificationOfNewTrack ClassifyNewTrack(const G4Track* track) override {
        // Kill neutrons below 1 keV (biasing example)
        if (track->GetDefinition() == G4Neutron::Neutron()
            && track->GetKineticEnergy() < 1.*keV) {
            return fKill;
        }
        return fUrgent;  // default: add to urgent stack
    }
};
```

## Registration in main()

```cpp
G4RunManager* runManager = new G4RunManager;
runManager->SetUserInitialization(new MyDetectorConstruction);
runManager->SetUserInitialization(new MyPhysicsList);

// User actions registered via ActionInitialization
runManager->SetUserInitialization(new MyActionInitialization);
```

## Common Pitfalls

- **Thread safety (MT mode)**: use G4Accumulable or G4StatAnalysis for merging per-thread data; never use global variables.
- **Step limit**: very long steps → add G4StepLimiter in physics list.
- **Units**: Geant4 uses internal units (MeV, mm, ns); always multiply with `* MeV`, `* mm`, etc.
