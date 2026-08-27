import {DecimalPipe} from '@angular/common'
import {Component, Input} from '@angular/core'
import {FormsModule} from '@angular/forms'
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

@Component({
  selector: 'app-marey',
  imports: [DecimalPipe, FormsModule, ReplayBadgeComponent],
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

  /** Number of timesteps visible in the chart height at once ("zoom level" of the sliding window). */
  @Input() visibleTimeSteps: number = 60
  /** Fixed spacing (in timesteps) between y-axis gridlines/labels, independent of the window size. */
  @Input() timeGridStep: number = 5

  get chartWidth(): number {
    return this.svgWidth - this.marginLeft - this.marginRight
  }

  get chartHeight(): number {
    return this.svgHeight - this.marginTop - this.marginBottom
  }

  /** First visible timestep (top of the sliding window). */
  public scrollOffset: number = 0
  /** While true, the window keeps scrolling to follow NOW (or the replay cursor); cleared on manual scroll. */
  public autoFollow: boolean = true

  /** Highest timestep present in either the actual history or any loaded plan, used only to size the scrollbar. */
  get contentMaxTime(): number {
    let max = this.timestep
    for (const train of this.trainRuns) {
      for (const coord of train.coordinates) max = Math.max(max, coord.t)
    }
    for (const plan of this.plannedRuns) {
      for (const train of plan) {
        for (const coord of train.coordinates) max = Math.max(max, coord.t)
      }
    }
    return max
  }

  get maxScrollOffset(): number {
    return Math.max(0, this.contentMaxTime - this.visibleTimeSteps)
  }

  /** Gridline/label positions, fixed at every `timeGridStep` timesteps within the visible window. */
  get timeTicks(): number[] {
    const ticks: number[] = []
    const first = Math.ceil(this.scrollOffset / this.timeGridStep) * this.timeGridStep
    for (let t = first; t <= this.scrollOffset + this.visibleTimeSteps; t += this.timeGridStep) {
      ticks.push(t)
    }
    return ticks
  }

  /** Fixed timestep-to-pixel mapping: unlike the old auto-fit scale, this does not change as history grows,
   * so a given timestep always maps to the same chart position while it stays inside the visible window. */
  timeToY(t: number): number {
    return this.marginTop + ((t - this.scrollOffset) / this.visibleTimeSteps) * this.chartHeight
  }

  private clampScroll(value: number): number {
    return Math.min(Math.max(0, value), this.maxScrollOffset)
  }

  private updateAutoScroll(): void {
    if (!this.autoFollow) return
    const target = this.replayTime ?? this.timestep
    this.scrollOffset = this.clampScroll(target - this.visibleTimeSteps * 0.7)
  }

  public scrollUp(): void {
    this.autoFollow = false
    this.scrollOffset = this.clampScroll(this.scrollOffset - this.timeGridStep)
  }

  public scrollDown(): void {
    this.autoFollow = false
    this.scrollOffset = this.clampScroll(this.scrollOffset + this.timeGridStep)
  }

  public onScrollInput(value: number): void {
    this.autoFollow = false
    this.scrollOffset = this.clampScroll(value)
  }

  public jumpToNow(): void {
    this.autoFollow = true
    this.updateAutoScroll()
  }

  public setVisibleTimeSteps(value: number): void {
    this.visibleTimeSteps = Math.max(this.timeGridStep, Math.round(value) || this.visibleTimeSteps)
    this.scrollOffset = this.clampScroll(this.scrollOffset)
    this.updateAutoScroll()
  }

  public maxDistance: number = 0

  public trainRuns: Array<TrainRun> = []
  public agents: Array<Agent> = []
  public timestep: number = 0

  public plannedRuns: Array<Array<TrainRun>> = []
  public selectedPlan?: number

  get nowY(): number {
    return this.timeToY(this.timestep)
  }

  public replayTime: number | null = null

  get replayY(): number {
    return this.timeToY(this.replayTime ?? 0)
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
      this.updateAutoScroll()
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
      this.updateAutoScroll()
    })
    this.stateService.getPlans().subscribe((plans) => {
      // Plans are always rebuilt from scratch on every emission (backend recomputes fresh each
      // step; old plans are never merged with new ones), so this can just discard prior state.
      this.plannedRuns = plans.map((plan) => {
        const agentHistories = plan
          .map((timestep, t) => ({timestep, t}))
          .filter(({t}) => t >= this.timestep)
          .reduce((agentHistory: Record<string, Array<{ agent: Agent; t: number }>>, {timestep, t}) => {
            for (const agent in timestep) {
              agentHistory[agent] ??= []
              agentHistory[agent].push({agent: timestep[agent], t})
            }
            return agentHistory
          }, {})
        return Object.entries(agentHistories).map(([name, coordinates]) => {
          return {
            name,
            coordinates: coordinates
              .map(({agent: {position}, t}) => ({
                x: position?.[0] ?? undefined,
                y: position?.[1] ?? undefined,
                t,
              }))
              .filter((coord): coord is { x: number; y: number; t: number } => coord.x !== undefined),
          }
        })
      })
      this.updateAutoScroll()
    })
    this.stateService.getTransitions().subscribe(() => {
      this.trainRuns = []
      this.plannedRuns = []
      this.timestep = 0
      this.scrollOffset = 0
      this.autoFollow = true
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
          y: this.timeToY(coord.t),
        }
      } else if (last !== null) {
        points.push(last)
        last = null
      }
    }
    if (last !== null) points.push(last)
    return points
  }

  /** Labels for one plan's agents, merging agents whose route ends at the same place and time
   * (e.g. identical source and target) into a single "id/id/id" label instead of stacking them. */
  getPlanLabels(plan: TrainRun[]): Array<{ x: number; y: number; label: string }> {
    const grouped = new Map<string, { x: number; y: number; names: string[] }>()
    for (const train of plan) {
      for (const endPoint of this.getPolylineSegmentEndPoints(train.coordinates)) {
        const key = `${endPoint.x.toFixed(2)},${endPoint.y.toFixed(2)}`
        const group = grouped.get(key)
        if (group) {
          group.names.push(train.name ?? '')
        } else {
          grouped.set(key, {x: endPoint.x, y: endPoint.y, names: [train.name ?? '']})
        }
      }
    }
    return Array.from(grouped.values()).map(({x, y, names}) => ({x, y, label: names.join('/')}))
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
      const y = this.timeToY(coord.t)
      parts.push(penDown ? `L ${x},${y}` : `M ${x},${y}`)
      penDown = true
    }
    return parts.join(' ')
  }
}
