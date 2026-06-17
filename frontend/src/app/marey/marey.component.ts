import {DecimalPipe} from '@angular/common'
import {Component, Input} from '@angular/core'
import {StateService} from '../state.service'
import {ControllerService} from '../controller.service'
import {Agent, DataService} from '../data.service'
import {firstValueFrom} from 'rxjs'

export interface TrainCoordinate {
  x: number
  y: number
  t: number
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
        max = Math.max(max, coord.t)
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

  public mapping: Record<string, unknown> = {}
  public startStationName = ''
  public endStationName = ''
  public selectedLineLabel = ''
  public trajectoryId: string | null = null

  constructor(
    public stateService: StateService,
    public controllerService: ControllerService,
    private dataService: DataService,
  ) {
  }

  ngOnInit() {
    this.stateService.getTrajectoryId().subscribe((trajectoryId) => {this.trajectoryId = trajectoryId})
    this.stateService.getSelectedLine().subscribe((selectedLine) => {
      this.updateLine(parseInt(selectedLine));
    })
    this.stateService.getPlan().subscribe((planIndex) => {
      this.selectedPlan = planIndex
    })
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
            .map(({position}, index) => ({
              x: position?.[0] ?? undefined,
              y: position?.[1] ?? undefined,
              t: index,
            }))
            .filter((coord): coord is { x: number; y: number; t: number } => coord.x !== undefined),
        }
      })
    })
    this.stateService.getPlans().subscribe((plans) => {
      this.plannedRuns = plans.map((plan) => {
        const agentHistories = plan
          .filter((_, index) => index >= this.timestep)
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
              .map(({position}, index) => ({
                x: position?.[0] ?? undefined,
                y: position?.[1] ?? undefined,
                t: index,
              }))
              .filter((coord): coord is { x: number; y: number; t: number } => coord.x !== undefined),
          }
        })
      })
    })
    this.controllerService.observeReset().subscribe(() => {
      this.trainRuns = []
      this.plannedRuns = []
      this.timestep = 0
      this.updateLine(0)
    })
  }

  private updateLine(lineIndex: number) {
    if (!this.trajectoryId || !lineIndex) return

    this.dataService.getTrajectoryLines(this.trajectoryId).then((lines) => {
      const line = lines[lineIndex]
      if (line) {
        this.startStationName = `City ${line.city_from}`
        this.endStationName = `City ${line.city_to}`
        this.selectedLineLabel = `Line ${lineIndex} (city ${line.city_from} → ${line.city_to})`
      }
    })
    this.dataService.getTrajectoryLineTransitions(this.trajectoryId, `${lineIndex}`)
      .then(data =>
        firstValueFrom(this.stateService.getAgents()).then(agents => {
          this.mapping = data.mapping
          this.maxDistance = data.grid[0].length
        })
      )
  }

  public getZwlPosition(coord: TrainCoordinate): [number, number] | null {
    const key = `(${coord.x}, ${coord.y})`

    const val = this.mapping[key]
    if (Array.isArray(val) && val.length >= 2) {
      return [val[0] as number, val[1] as number]
    }
    return null
  }


  getPolylinePoints(coordinates: TrainCoordinate[], i: string): string {
    let polyPoints = coordinates
      .map((coord) => {
        const zwlPos = this.getZwlPosition(coord)
        if (zwlPos === null) {
          return null
        }
        const x = this.marginLeft + (zwlPos[1] / this.maxDistance) * this.chartWidth
        const y = this.marginTop + (coord.t / this.maxTime) * this.chartHeight
        return `${x},${y}`
      })
      .filter((v) => v != null)
      .join(' ');
    if (i == "0") {
      console.log(`${i}: ${polyPoints} ${coordinates}`)
    }
    return polyPoints
  }
}
