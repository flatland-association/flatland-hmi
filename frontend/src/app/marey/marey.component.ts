import {DecimalPipe} from '@angular/common'
import {Component, Input} from '@angular/core'
import {StateService} from '../state.service'
import {Agent} from '../data.service'
import {combineLatest} from 'rxjs'
import {ReplayBadgeComponent} from '../replay-badge/replay-badge.component'

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
  imports: [DecimalPipe, ReplayBadgeComponent],
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

  get nowY(): number {
    return this.marginTop + (this.timestep / this.maxTime) * this.chartHeight
  }

  public replayTime: number | null = null

  get replayY(): number {
    return this.marginTop + ((this.replayTime ?? 0) / this.maxTime) * this.chartHeight
  }

  public mapping: Map<number, Map<number, [number, number]>> = new Map()
  public fromGate = ''
  public toGate = ''
  public selectedLinkLabel = ''
  public selectedLink: number = 0

  constructor(
    public stateService: StateService,
  ) {
  }

  ngOnInit() {
    combineLatest([
      this.stateService.getLinks(),
      this.stateService.getLinkMap(),
      this.stateService.getSelectedLink(),
    ]).subscribe(([links, data, selectedLink]) => {
      this.selectedLink = parseInt(selectedLink)
      const link = links[this.selectedLink]
      if (link) {
        this.fromGate = link.fromGate
        this.toGate = link.toGate
        this.selectedLinkLabel = link.label
      }
      this.mapping = new Map()
      for (const [[r, c], [mr, mc]] of data.mapping) {
        if (!this.mapping.has(r)) this.mapping.set(r, new Map())
        this.mapping.get(r)!.set(c, [mr, mc])
      }
      this.maxDistance = data.grid[0].length
    })
    this.stateService.getPlan().subscribe((planIndex) => {
      this.selectedPlan = planIndex
    })
    this.stateService.getReplayTime().subscribe((replayTime) => {
      this.replayTime = replayTime
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
    this.stateService.getTransitions().subscribe(() => {
      this.trainRuns = []
      this.plannedRuns = []
      this.timestep = 0
    })
  }

  public getZwlPosition(coord: TrainCoordinate): [number, number] | null {
    return this.mapping.get(coord.x)?.get(coord.y) ?? null
  }


  getPolylineSegmentEndPoints(coordinates: TrainCoordinate[]): { x: number; y: number }[] {
    const points: { x: number; y: number }[] = []
    let last: { x: number; y: number } | null = null
    for (const coord of coordinates) {
      const zwlPos = this.getZwlPosition(coord)
      if (zwlPos !== null) {
        last = {
          x: this.marginLeft + (zwlPos[1] / this.maxDistance) * this.chartWidth,
          y: this.marginTop + (coord.t / this.maxTime) * this.chartHeight,
        }
      } else if (last !== null) {
        points.push(last)
        last = null
      }
    }
    if (last !== null) points.push(last)
    return points
  }

  getPolylinePath(coordinates: TrainCoordinate[]): string {
    const parts: string[] = []
    let penDown = false
    for (const coord of coordinates) {
      const zwlPos = this.getZwlPosition(coord)
      if (zwlPos === null) {
        penDown = false
        continue
      }
      const x = this.marginLeft + (zwlPos[1] / this.maxDistance) * this.chartWidth
      const y = this.marginTop + (coord.t / this.maxTime) * this.chartHeight
      parts.push(penDown ? `L ${x},${y}` : `M ${x},${y}`)
      penDown = true
    }
    return parts.join(' ')
  }
}
