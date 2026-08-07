import { TestBed } from '@angular/core/testing'
import { firstValueFrom } from 'rxjs'

import { StateService } from './state.service'
import { Agent, TrajectoryStep } from './data.service'

describe('StateService', () => {
  let service: StateService

  beforeEach(() => {
    TestBed.configureTestingModule({})
    service = TestBed.inject(StateService)
  })

  function makeAgent(handle: number, position: [number, number]): Agent {
    return { handle, position, direction: 0, moving: true, target: [0, 0], malfunction: 0 }
  }

  function makeStep(elapsedSteps: number, done = false): TrajectoryStep {
    return { ep_id: 'ep-1', policy_id: 'policy-0', env_id: 'env-0', elapsed_steps: elapsedSteps, done }
  }

  describe('plans', () => {
    it('starts with no plans', async () => {
      expect(await firstValueFrom(service.getPlans())).toEqual([])
    })

    it('publishes plans set via setPlans', async () => {
      const plans = [[{ '0': makeAgent(0, [1, 1]) }]]
      service.setPlans(plans)
      expect(await firstValueFrom(service.getPlans())).toBe(plans)
    })

    it('clearHistory resets plans back to empty', async () => {
      service.setPlans([[{ '0': makeAgent(0, [1, 1]) }]])
      service.clearHistory()
      expect(await firstValueFrom(service.getPlans())).toEqual([])
    })
  })

  describe('replay time (time machine)', () => {
    it('starts live (replay time is null)', async () => {
      expect(await firstValueFrom(service.getReplayTime())).toBeNull()
    })

    it('publishes the replay time set via setReplayTime', async () => {
      service.setReplayTime(3)
      expect(await firstValueFrom(service.getReplayTime())).toBe(3)
    })

    it('clearHistory resets replay time back to live (null)', async () => {
      service.setReplayTime(3)
      service.clearHistory()
      expect(await firstValueFrom(service.getReplayTime())).toBeNull()
    })
  })

  describe('getDisplayedAgents', () => {
    it('returns the live agents while not replaying', async () => {
      const liveAgents = [makeAgent(0, [5, 5])]
      service.loadTrajectory([], liveAgents, { stationEdges: {}, stationGates: {}, stationStoppingPoints: {} })

      expect(await firstValueFrom(service.getDisplayedAgents())).toEqual(liveAgents)
    })

    it('returns the historical snapshot at the replay time instead of the live agents', async () => {
      // Step 1: agent at [1, 1]. Step 2: agent at [2, 2] (now live).
      service.applyStep(makeStep(1), [makeAgent(0, [1, 1])])
      service.applyStep(makeStep(2), [makeAgent(0, [2, 2])])

      service.setReplayTime(1)

      const displayed = await firstValueFrom(service.getDisplayedAgents())
      expect(displayed).toEqual([makeAgent(0, [1, 1])])
    })

    it('falls back to the live agents when the replay time has no matching history entry', async () => {
      service.applyStep(makeStep(1), [makeAgent(0, [1, 1])])
      service.setReplayTime(99)

      expect(await firstValueFrom(service.getDisplayedAgents())).toEqual([makeAgent(0, [1, 1])])
    })

    it('returns to the live agents once replay is left (replay time set back to null)', async () => {
      service.applyStep(makeStep(1), [makeAgent(0, [1, 1])])
      service.applyStep(makeStep(2), [makeAgent(0, [2, 2])])
      service.setReplayTime(1)
      service.setReplayTime(null)

      expect(await firstValueFrom(service.getDisplayedAgents())).toEqual([makeAgent(0, [2, 2])])
    })
  })
})
