import { DecimalPipe } from '@angular/common'
import { Component, Input } from '@angular/core'
import { StateService } from '../state.service'
import { Agent } from '../data.service'
import { ControllerService, State } from '../controller.service'

export interface TrainCoordinate {
  x: number
  y: number
}

export interface TrainRun {
  name?: string
  coordinates: TrainCoordinate[]
}

const PLAN_CUTTOFF = 20

@Component({
  selector: 'app-marey',
  imports: [DecimalPipe],
  templateUrl: './marey.component.html',
  styleUrl: './marey.component.scss',
})
export class MareyComponent {
  @Input() svgWidth: number = 600
  @Input() svgHeight: number = 400
  @Input() marginLeft: number = 50
  @Input() marginTop: number = 50
  @Input() marginRight: number = 50
  @Input() marginBottom: number = 50

  get chartWidth(): number {
    return this.svgWidth - this.marginLeft - this.marginRight
  }

  get chartHeight(): number {
    return this.svgHeight - this.marginTop - this.marginBottom
  }

  get maxTime(): number {
    if (this.trainRuns.length === 0) return 50

    let max = 0
    this.trainRuns.forEach((train) => {
      train.coordinates.forEach((coord) => {
        max = Math.max(max, coord.y)
      })
    })
    return max + PLAN_CUTTOFF
  }

  public maxDistance: number = 0

  public trainRuns: Array<TrainRun> = []
  public agents: Array<Agent> = []
  public timestep: number = 0

  public plannedRuns: Array<Array<TrainRun>> = []
  public selectedPlan?: number

  constructor(
    public stateService: StateService,
    public controllerService: ControllerService,
  ) {}

  ngOnInit() {
    this.stateService.getTransitions().subscribe((transitions) => (this.maxDistance = transitions[0].length - 1))
    this.stateService.getHistory().subscribe((history) => {
      this.timestep = history.length
      const agentHistories = history.reduce((agentHistory: Record<string, Agent[]>, timestep) => {
        for (const agent in timestep) {
          agentHistory[agent] ??= []
          agentHistory[agent].push(timestep[agent])
        }
        return agentHistory
      }, {})
      this.trainRuns = Object.entries(agentHistories).map(([name, coordinates]) => {
        return {
          name,
          coordinates: coordinates
            .map(({ position }, index) => ({
              x: position?.[1] ?? undefined,
              y: index,
            }))
            .filter((coord): coord is { x: number; y: number } => coord.x !== undefined),
        }
      })
    })
    this.stateService.getPlans().subscribe((plans) => {
      this.plannedRuns = plans.map((plan) => {
        const agentHistories = plan
          .filter((_, index) => index > this.timestep)
          .reduce((agentHistory: Record<string, Agent[]>, timestep) => {
            for (const agent in timestep) {
              agentHistory[agent] ??= []
              agentHistory[agent].push(timestep[agent])
            }
            return agentHistory
          }, {})
        return Object.entries(agentHistories).map(([name, coordinates]) => {
          return {
            name,
            coordinates: coordinates
              .map(({ position }, index) => ({
                x: position?.[1] ?? undefined,
                y: this.timestep + 1 + index,
              }))
              .filter(
                (coord, index): coord is { x: number; y: number } => coord.x !== undefined && index < PLAN_CUTTOFF,
              ),
          }
        })
      })
    })
    this.controllerService.observeReset().subscribe(() => {
      this.trainRuns = []
      this.plannedRuns = []
    })
  }

  getPolylinePoints(coordinates: TrainCoordinate[]): string {
    return coordinates
      .map((coord) => {
        const x = this.marginLeft + (coord.x / this.maxDistance) * this.chartWidth
        const y = this.marginTop + (coord.y / this.maxTime) * this.chartHeight
        return `${x},${y}`
      })
      .join(' ')
  }
}
