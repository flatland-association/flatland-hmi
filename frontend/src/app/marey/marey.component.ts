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
    return Math.max(max, 20)
  }

  public maxDistance: number = 0

  public trainRuns: TrainRun[] = []
  public agents: Array<Agent> = []
  public history?: Array<Array<{ x: number; y: number }>>

  constructor(
    public stateService: StateService,
    public controllerService: ControllerService,
  ) {}

  ngOnInit() {
    this.stateService.getTransitions().subscribe((transitions) => (this.maxDistance = transitions[0].length - 1))
    this.stateService.getAgents().subscribe((agents) => {
      this.agents = agents
      if (!this.history) {
        this.history = agents.map(() => [])
      }
      for (let i = 0; i < agents.length; i++) {
        const agent = agents[i]
        if (agent.position) {
          const x = agent.position[1]
          const y = this.history.reduce((maxY, coords) => Math.max(coords.length, maxY), 0)
          this.history[i].push({ x, y })
        }
      }
      this.trainRuns = agents.map((_, index) => ({
        name: `${index}`,
        coordinates: this.history?.[index] ?? [],
      }))
    })
    this.controllerService.observeReset().subscribe(() => {
      this.history = undefined
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
