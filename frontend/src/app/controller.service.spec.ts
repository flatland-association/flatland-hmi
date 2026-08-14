import { fakeAsync, TestBed, tick } from '@angular/core/testing'

import { ControllerService } from './controller.service'
import { DataService, Agent, TrajectoryStep } from './data.service'
import { StateService } from './state.service'

describe('ControllerService', () => {
  let controller: ControllerService
  let dataServiceSpy: jasmine.SpyObj<DataService>
  let stateServiceSpy: jasmine.SpyObj<StateService>

  const stations = { stationEdges: {}, stationGates: {}, stationStoppingPoints: {} }

  function makeAgent(handle: number): Agent {
    return { handle, position: [0, 0], direction: 0, moving: true, target: [0, 0], malfunction: 0 }
  }

  function makeStep(elapsedSteps: number, done = false): TrajectoryStep {
    return { ep_id: 'traj-1', policy_id: 'policy-a', env_id: 'env-a', elapsed_steps: elapsedSteps, done }
  }

  beforeEach(() => {
    dataServiceSpy = jasmine.createSpyObj<DataService>('DataService', [
      'getEnvs',
      'getPolicies',
      'createTrajectory',
      'getTrajectoryLinks',
      'getTrajectoryLinkMap',
      'getTrajectoryTransitions',
      'getTrajectoryAgents',
      'getTrajectoryStations',
      'getTrajectoryAgentPlans',
      'stepTrajectory',
    ])
    // Prevent the constructor's own startup logic (which would call reset()) from interfering.
    dataServiceSpy.getEnvs.and.resolveTo([])
    dataServiceSpy.getPolicies.and.resolveTo([])
    dataServiceSpy.getTrajectoryLinks.and.resolveTo([])
    dataServiceSpy.getTrajectoryLinkMap.and.resolveTo({ grid: [], mapping: [], levels: [], incompleteCells: [] })

    stateServiceSpy = jasmine.createSpyObj<StateService>('StateService', [
      'clearHistory',
      'loadTrajectory',
      'setPlans',
      'applyStep',
      'setLinks',
      'setEnvs',
      'setPolicies',
      'selectLink',
      'setLinkMap',
    ])
    stateServiceSpy.applyStep.and.returnValue({ steps: 1, done: { __all__: false } })

    TestBed.configureTestingModule({
      providers: [
        { provide: DataService, useValue: dataServiceSpy },
        { provide: StateService, useValue: stateServiceSpy },
      ],
    })
    controller = TestBed.inject(ControllerService)
  })

  describe('reset()', () => {
    it('clears history before creating the new trajectory (resets the time machine too)', fakeAsync(() => {
      dataServiceSpy.createTrajectory.and.resolveTo('traj-1')
      dataServiceSpy.getTrajectoryTransitions.and.resolveTo([])
      dataServiceSpy.getTrajectoryAgents.and.resolveTo([])
      dataServiceSpy.getTrajectoryStations.and.resolveTo(stations)
      dataServiceSpy.getTrajectoryAgentPlans.and.resolveTo([])

      controller.reset('env-a', 'policy-a')

      expect(stateServiceSpy.clearHistory).toHaveBeenCalledBefore(dataServiceSpy.createTrajectory)
      tick()
    }))

    it('fetches agent plans alongside transitions/agents/stations and publishes them via state', fakeAsync(() => {
      const agents = [makeAgent(0)]
      const plans = [[{ '0': makeAgent(0) }]]
      dataServiceSpy.createTrajectory.and.resolveTo('traj-1')
      dataServiceSpy.getTrajectoryTransitions.and.resolveTo([])
      dataServiceSpy.getTrajectoryAgents.and.resolveTo(agents)
      dataServiceSpy.getTrajectoryStations.and.resolveTo(stations)
      dataServiceSpy.getTrajectoryAgentPlans.and.resolveTo(plans)

      controller.reset('env-a', 'policy-a')
      tick()

      expect(dataServiceSpy.getTrajectoryAgentPlans).toHaveBeenCalledWith('traj-1')
      expect(stateServiceSpy.loadTrajectory).toHaveBeenCalledWith([], agents, stations)
      expect(stateServiceSpy.setPlans).toHaveBeenCalledWith(plans)
    }))

    it('does nothing when environment or policy is missing', () => {
      controller.reset(undefined, 'policy-a')
      controller.reset('env-a', undefined)

      expect(stateServiceSpy.clearHistory).not.toHaveBeenCalled()
      expect(dataServiceSpy.createTrajectory).not.toHaveBeenCalled()
    })
  })

  describe('stepping', () => {
    beforeEach(fakeAsync(() => {
      // Establish a current trajectory via reset() so next()/step() have something to act on.
      dataServiceSpy.createTrajectory.and.resolveTo('traj-1')
      dataServiceSpy.getTrajectoryTransitions.and.resolveTo([])
      dataServiceSpy.getTrajectoryAgents.and.resolveTo([])
      dataServiceSpy.getTrajectoryStations.and.resolveTo(stations)
      dataServiceSpy.getTrajectoryAgentPlans.and.resolveTo([])
      controller.reset('env-a', 'policy-a')
      tick()
    }))

    it('fetches agent plans on every step', fakeAsync(() => {
      const agents = [makeAgent(0)]
      const plans = [[{ '0': makeAgent(0) }]]
      dataServiceSpy.stepTrajectory.and.resolveTo(makeStep(1))
      dataServiceSpy.getTrajectoryAgents.and.resolveTo(agents)
      dataServiceSpy.getTrajectoryAgentPlans.and.resolveTo(plans)

      controller.next()
      tick()

      expect(dataServiceSpy.getTrajectoryAgentPlans).toHaveBeenCalledWith('traj-1')
      expect(stateServiceSpy.setPlans).toHaveBeenCalledWith(plans)
    }))

    it('applies the step before publishing plans, so Marey reads the up-to-date timestep', fakeAsync(() => {
      const callOrder: string[] = []
      stateServiceSpy.applyStep.and.callFake(() => {
        callOrder.push('applyStep')
        return { steps: 1, done: { __all__: false } }
      })
      stateServiceSpy.setPlans.and.callFake(() => {
        callOrder.push('setPlans')
      })
      dataServiceSpy.stepTrajectory.and.resolveTo(makeStep(1))
      dataServiceSpy.getTrajectoryAgents.and.resolveTo([makeAgent(0)])
      dataServiceSpy.getTrajectoryAgentPlans.and.resolveTo([])

      controller.next()
      tick()

      expect(callOrder).toEqual(['applyStep', 'setPlans'])
    }))

    it('stops draining the step queue once the episode is done', fakeAsync(() => {
      dataServiceSpy.stepTrajectory.and.resolveTo(makeStep(1, true))
      dataServiceSpy.getTrajectoryAgents.and.resolveTo([])
      dataServiceSpy.getTrajectoryAgentPlans.and.resolveTo([])
      stateServiceSpy.applyStep.and.returnValue({ steps: 1, done: { __all__: true } })

      controller.play()
      controller.next()
      tick()

      expect(controller.playing).toBeFalse()
    }))
  })
})
