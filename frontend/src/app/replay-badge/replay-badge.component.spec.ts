import { ReplayBadgeComponent } from './replay-badge.component'
import { StateService } from '../state.service'
import { Agent, TrajectoryStep } from '../data.service'

describe('ReplayBadgeComponent', () => {
  let stateService: StateService
  let component: ReplayBadgeComponent

  function makeAgent(handle: number): Agent {
    return { handle, position: [0, 0], direction: 0, moving: true, target: [0, 0], malfunction: 0 }
  }

  function makeStep(elapsedSteps: number): TrajectoryStep {
    return { ep_id: 'ep-1', policy_id: 'policy-0', env_id: 'env-0', elapsed_steps: elapsedSteps, done: false }
  }

  beforeEach(() => {
    stateService = new StateService()
    component = new ReplayBadgeComponent(stateService)
    component.ngOnInit()
  })

  it('is LIVE (not replaying, not future) by default', () => {
    expect(component.replaying).toBeFalse()
    expect(component.future).toBeFalse()
  })

  it('is REPLAY (replaying, not future) when the replay time is within history', () => {
    stateService.applyStep(makeStep(1), [makeAgent(0)])
    stateService.applyStep(makeStep(2), [makeAgent(0)])
    stateService.setReplayTime(1)

    expect(component.replaying).toBeTrue()
    expect(component.future).toBeFalse()
  })

  it('is FUTURE (replaying, and future) when the replay time is beyond history', () => {
    stateService.applyStep(makeStep(1), [makeAgent(0)])
    stateService.setReplayTime(2)

    expect(component.replaying).toBeTrue()
    expect(component.future).toBeTrue()
  })

  it('returns to LIVE once replay is left', () => {
    stateService.applyStep(makeStep(1), [makeAgent(0)])
    stateService.setReplayTime(2)
    stateService.setReplayTime(null)

    expect(component.replaying).toBeFalse()
    expect(component.future).toBeFalse()
  })
})
