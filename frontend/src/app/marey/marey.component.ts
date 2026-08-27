import {DecimalPipe} from '@angular/common'
import {Component, Input} from '@angular/core'
import {FormsModule} from '@angular/forms'
import {StateService} from '../state.service'
import {Agent, StationsResponse} from '../data.service'
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

/** Pixels per distance unit, matching the fixed 20px cell size of the link map's grid so the two stay aligned. */
const CELL_PX = 20

@Component({
  selector: 'app-marey',
  imports: [DecimalPipe, FormsModule, ReplayBadgeComponent],
  templateUrl: './marey.component.html',
  styleUrl: './marey.component.scss',
})
export class MareyComponent {
  @Input() svgHeight: number = 400
  @Input() marginLeft: number = 50
  @Input() marginTop: number = 50
  @Input() marginRight: number = 50
  @Input() marginBottom: number = 50

  /** Number of timesteps visible in the chart height at once ("zoom level" of the sliding window). */
  @Input() visibleTimeSteps: number = 60
  /** Fixed spacing (in timesteps) between y-axis gridlines/labels, independent of the window size. */
  @Input() timeGridStep: number = 5
  /** A horizontal jump larger than this many distance-axis cells between consecutive timesteps lifts the pen
   * (breaks the polyline) instead of drawing a diagonal line across the gap. */
  @Input() maxJumpDistance: number = 5

  /** Matches the link map's grid width exactly (maxDistance columns at CELL_PX each) so the two charts line up. */
  get chartWidth(): number {
    return Math.max(this.maxDistance, 1) * CELL_PX
  }

  get svgWidth(): number {
    return this.marginLeft + this.chartWidth + this.marginRight
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

  /** Station areas (orange overlay), as distance-axis column ranges within the currently mapped link. */
  public stationBands: Array<{ name: string; fromDistance: number; toDistance: number }> = []
  /** Station pins (red overlay, matching the link map's pin cells), as a distance-axis column. */
  public pinBands: Array<{ name: string; distance: number }> = []
  /** Stopping points (red vertical line), as a distance-axis column within the currently mapped link. */
  public stoppingPoints: Array<{ name: string; distance: number }> = []

  constructor(
    public stateService: StateService,
  ) {
  }

  ngOnInit() {
    combineLatest([
      this.stateService.getLinks(),
      this.stateService.getLinkMap(),
      this.stateService.getSelectedLink(),
      this.stateService.getStations(),
    ]).subscribe(([links, data, selectedLink, stations]) => {
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
      this.computeStationOverlays(stations)
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

  distanceToX(distance: number): number {
    return this.marginLeft + (distance / Math.max(this.maxDistance, 1)) * this.chartWidth
  }

  /** Pixel width of one distance unit (one link-map cell). */
  get cellWidth(): number {
    return this.distanceToX(1) - this.distanceToX(0)
  }

  /** Station areas, pins, and stopping points along the currently selected link, transformed from env into
   * ZWL/distance coordinates the same way LinkMapComponent does, so they line up with the trajectories plotted
   * below. Pins are colored like the link map's pin cells (red), taking priority over the station's orange area. */
  private computeStationOverlays(stations: StationsResponse): void {
    const mapDistance = ([r, c]: [number, number]): number | undefined => this.mapping.get(r)?.get(c)?.[1]

    this.stationBands = Object.entries(stations.stationEdges)
      .map(([name, cells]) => {
        const distances = cells.map(mapDistance).filter((d): d is number => d !== undefined)
        if (distances.length === 0) return null
        return {name, fromDistance: Math.min(...distances), toDistance: Math.max(...distances)}
      })
      .filter((band): band is { name: string; fromDistance: number; toDistance: number } => band !== null)

    this.pinBands = Object.values(stations.stationGates)
      .flatMap((gates) => Object.values(gates))
      .flatMap((gate) => Object.values(gate.pins))
      .map((pin) => ({name: pin.name, distance: mapDistance(pin.node)}))
      .filter((pin): pin is { name: string; distance: number } => pin.distance !== undefined)

    this.stoppingPoints = Object.entries(stations.stationStoppingPoints)
      .flatMap(([name, points]) => points.map((stp) => ({name, distance: mapDistance(stp.node)})))
      .filter((stp): stp is { name: string; distance: number } => stp.distance !== undefined)
  }

  /** True if consecutive timesteps jump more than `maxJumpDistance` cells along the distance axis — e.g. a
   * fresh agent respawning at a different position — in which case the polyline should lift its pen there
   * rather than draw a diagonal line across the gap. */
  private isBigJump(lastDistance: number | null, distance: number): boolean {
    return lastDistance !== null && Math.abs(distance - lastDistance) > this.maxJumpDistance
  }

  getPolylineSegmentEndPoints(coordinates: TrainCoordinate[]): { x: number; y: number }[] {
    const points: { x: number; y: number }[] = []
    let last: { x: number; y: number } | null = null
    let lastDistance: number | null = null
    for (const coord of coordinates) {
      const zwlPos = this.getZwlPosition(coord)
      if (zwlPos !== null && !this.isBigJump(lastDistance, zwlPos[1])) {
        last = {
          x: this.distanceToX(zwlPos[1]),
          y: this.timeToY(coord.t),
        }
        lastDistance = zwlPos[1]
      } else {
        if (last !== null) points.push(last)
        last = null
        lastDistance = zwlPos !== null ? zwlPos[1] : null
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
    let lastDistance: number | null = null
    for (const coord of coordinates) {
      const zwlPos = this.getZwlPosition(coord)
      if (zwlPos === null) {
        penDown = false
        lastDistance = null
        continue
      }
      if (this.isBigJump(lastDistance, zwlPos[1])) {
        penDown = false
      }
      const x = this.distanceToX(zwlPos[1])
      const y = this.timeToY(coord.t)
      parts.push(penDown ? `L ${x},${y}` : `M ${x},${y}`)
      penDown = true
      lastDistance = zwlPos[1]
    }
    return parts.join(' ')
  }

  /** Points where the polyline's pen lifts or drops — i.e. both ends of every continuous segment produced by
   * `getPolylinePath` (a missing position, or a jump bigger than `maxJumpDistance`, each start a new segment) —
   * rendered as small "lollipop" markers so the viewer can tell a break in the line from a genuine gap in data. */
  getPolylineBreakPoints(coordinates: TrainCoordinate[]): { x: number; y: number }[] {
    const points: { x: number; y: number }[] = []
    let penDown = false
    let pendingPenUp: { x: number; y: number } | null = null
    let lastDistance: number | null = null
    for (const coord of coordinates) {
      const zwlPos = this.getZwlPosition(coord)
      if (zwlPos === null) {
        if (pendingPenUp !== null) points.push(pendingPenUp)
        pendingPenUp = null
        penDown = false
        lastDistance = null
        continue
      }
      if (this.isBigJump(lastDistance, zwlPos[1])) {
        if (pendingPenUp !== null) points.push(pendingPenUp)
        pendingPenUp = null
        penDown = false
      }
      const point = {x: this.distanceToX(zwlPos[1]), y: this.timeToY(coord.t)}
      if (!penDown) points.push(point)
      pendingPenUp = point
      penDown = true
      lastDistance = zwlPos[1]
    }
    if (pendingPenUp !== null) points.push(pendingPenUp)
    return points
  }
}
