import { MareyComponent, TrainCoordinate, TrainRun } from './marey.component'
import { StateService } from '../state.service'

describe('MareyComponent marker computation', () => {
  let component: MareyComponent

  function coord(distance: number, t: number): TrainCoordinate {
    // getZwlPosition looks up mapping.get(x).get(y); using x=0 and y=distance keeps the fixture simple,
    // with the mapped column (zwlPos[1]) equal to `distance` for direct control over test data.
    return { x: 0, y: distance, t }
  }

  beforeEach(() => {
    // MareyComponent only uses stateService via ngOnInit's subscriptions, which these tests never trigger.
    component = new MareyComponent({} as StateService)
    component.mapping = new Map([
      [0, new Map([0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => [d, [0, d] as [number, number]]))],
    ])
  })

  describe('getSpawnMarker / getInternalBreakPoints / getPlanTargetMarker', () => {
    it('returns null spawn marker for an empty trajectory', () => {
      expect(component.getSpawnMarker([])).toBeNull()
    })

    it('returns the first point as the spawn marker', () => {
      const coords = [coord(1, 0), coord(2, 1)]
      expect(component.getSpawnMarker(coords)).toEqual(
        jasmine.objectContaining({ x: component.distanceToX(1), y: component.timeToY(0) }),
      )
    })

    it('has no internal break points for a single unbroken run', () => {
      const coords = [coord(1, 0), coord(2, 1), coord(3, 2)]
      expect(component.getInternalBreakPoints(coords)).toEqual([])
    })

    it('flags a break at a jump bigger than maxJumpDistance', () => {
      component.maxJumpDistance = 5
      const coords = [coord(1, 0), coord(9, 1)]
      const breaks = component.getInternalBreakPoints(coords)
      expect(breaks).toEqual([
        { x: component.distanceToX(1), y: component.timeToY(0) },
        { x: component.distanceToX(9), y: component.timeToY(1) },
      ])
    })

    it('returns the last point as the plan target marker', () => {
      const coords = [coord(1, 0), coord(2, 1)]
      expect(component.getPlanTargetMarker(coords)).toEqual(
        jasmine.objectContaining({ x: component.distanceToX(2), y: component.timeToY(1) }),
      )
    })
  })

  describe('getActualEndMarker', () => {
    function train(coordinates: TrainCoordinate[]): TrainRun {
      return { name: 'A', coordinates }
    }

    it('returns null while the agent is still going and has no loaded plan', () => {
      component.timestep = 2
      component.plannedRuns = []
      expect(component.getActualEndMarker(train([coord(1, 0), coord(2, 1)]))).toBeNull()
    })

    it('returns a marker once the agent has genuinely finished before now', () => {
      component.timestep = 5
      component.plannedRuns = []
      const last = coord(2, 1)
      expect(component.getActualEndMarker(train([coord(1, 0), last]))).toEqual({
        x: component.distanceToX(2),
        y: component.timeToY(1),
      })
    })

    it('returns null when still going and the plan continues from the same distance', () => {
      component.timestep = 2
      component.plannedRuns = [[train([coord(2, 2), coord(3, 3)])]]
      expect(component.getActualEndMarker(train([coord(1, 0), coord(2, 1)]))).toBeNull()
    })

    it('flags a divergence when the plan predicts a different distance right at now', () => {
      component.timestep = 2
      component.plannedRuns = [[train([coord(9, 2), coord(8, 3)])]]
      const last = coord(2, 1)
      expect(component.getActualEndMarker(train([coord(1, 0), last]))).toEqual({
        x: component.distanceToX(2),
        y: component.timeToY(1),
      })
    })
  })

  describe('getPlannedStartMarker', () => {
    function train(coordinates: TrainCoordinate[]): TrainRun {
      return { name: 'A', coordinates }
    }

    it('is a double marker when the agent has no actual trajectory yet', () => {
      component.trainRuns = []
      const planned = train([coord(5, 2), coord(6, 3)])
      expect(component.getPlannedStartMarker(planned)).toEqual({
        x: component.distanceToX(5),
        y: component.timeToY(2),
        double: true,
      })
    })

    it('is null when the plan continues seamlessly from the actual trajectory', () => {
      component.trainRuns = [train([coord(1, 0), coord(2, 1)])]
      const planned = train([coord(2, 2), coord(3, 3)])
      expect(component.getPlannedStartMarker(planned)).toBeNull()
    })

    it('is a single marker when the plan diverges from the actual trajectory', () => {
      component.trainRuns = [train([coord(1, 0), coord(2, 1)])]
      const planned = train([coord(9, 2), coord(8, 3)])
      expect(component.getPlannedStartMarker(planned)).toEqual({
        x: component.distanceToX(9),
        y: component.timeToY(2),
        double: false,
      })
    })
  })
})
