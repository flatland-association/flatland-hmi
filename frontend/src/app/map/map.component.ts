import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import {combineLatest} from 'rxjs'
import {Agent, State} from '../data.service'
import {ControllerService} from '../controller.service'
import {FormsModule} from '@angular/forms';
import {ReplayBadgeComponent} from '../replay-badge/replay-badge.component'

interface SelectOption {
  value: string
  label: string
}

@Component({
  selector: 'app-map',
  imports: [FormsModule, ReplayBadgeComponent],
  templateUrl: './map.component.html',
  styleUrl: './map.component.scss',
})
export class MapComponent implements OnInit {
  public mapClasses: Array<Array<MapCell>> = []
  public agents: Array<Agent> = []
  public levelCoords = new Map<number, Map<number, number>>()
  public state: State = {
    steps: 0,
    done: {
      __all__: false,
    },
  }

  public policyOptions: SelectOption[] = []
  public currentPolicy = ''

  public envOptions: SelectOption[] = []
  public currentEnv = ''

  public nowTime = 0
  /** Furthest step the time machine can reach — beyond `nowTime` when a plan projects further into the future. */
  public maxReplayTime = 0
  public replayTime: number | null = null

  public get inReplayMode(): boolean {
    return this.replayTime !== null
  }

  public get displayedTime(): number {
    return this.replayTime ?? this.nowTime
  }


  constructor(
    public stateService: StateService,
    public controllerService: ControllerService,
    public rendererService: RendererService,
  ) {}

  ngOnInit() {
    this.stateService.getEnvs().subscribe(envs => {
      this.envOptions = envs.map(e => ({ value: e.id, label: e.description }))
      this.currentEnv = this.envOptions[0]?.value ?? ''
    })
    this.stateService.getPolicies().subscribe(policies => {
      this.policyOptions = policies.map(p => ({ value: p.id, label: p.description }))
      this.currentPolicy = this.policyOptions[0]?.value ?? ''
    })
    this.stateService.getState().subscribe((state) => (this.state = state))
    combineLatest([
      this.stateService.getTransitions(),
      this.stateService.getStations(),
    ]).subscribe(([transitions, stations]) => {
      this.mapClasses = this.rendererService.renderMap(transitions, [], stations)
    })
    this.stateService.getDisplayedAgents().subscribe((agents) => (this.agents = agents))
    this.stateService.getLinkMap().subscribe(data => {
      this.levelCoords = new Map()
      for (const [[r, c], level] of data.levels ?? []) {
        if (!this.levelCoords.has(r)) this.levelCoords.set(r, new Map())
        this.levelCoords.get(r)!.set(c, level)
      }
    })
    this.stateService.getHistory().subscribe((history) => (this.nowTime = history.length))
    this.stateService.getMaxReplayTime().subscribe((maxReplayTime) => (this.maxReplayTime = maxReplayTime))
    this.stateService.getReplayTime().subscribe((replayTime) => (this.replayTime = replayTime))
  }

  public getLevel(row: number, col: number): number | undefined {
    return this.levelCoords.get(row)?.get(col)
  }

  public getSteps() {
    return this.state?.steps ?? 0
  }

  public enterTimeMachine(): void {
    this.stateService.setReplayTime(Math.max(1, this.nowTime))
  }

  public leaveTimeMachine(): void {
    this.stateService.setReplayTime(null)
  }

  public timeMachinePrev(): void {
    if (this.replayTime === null) return
    this.stateService.setReplayTime(Math.max(1, this.replayTime - 1))
  }

  public timeMachineNext(): void {
    if (this.replayTime === null) return
    this.stateService.setReplayTime(Math.min(this.maxReplayTime, this.replayTime + 1))
  }

  public timeMachineJump(value: string): void {
    const step = parseInt(value, 10)
    if (isNaN(step)) return
    this.stateService.setReplayTime(Math.min(this.maxReplayTime, Math.max(1, step)))
  }
}
