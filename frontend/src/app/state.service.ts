import { Injectable } from '@angular/core'
import { Agent, DataService, StationsResponse, Transitions } from './data.service'
import { Observable, ReplaySubject } from 'rxjs'
import { ControllerService, State } from './controller.service'

@Injectable({
  providedIn: 'root',
})
export class StateService {
  private transitions = new ReplaySubject<Transitions>(1)
  private agents = new ReplaySubject<Array<Agent>>(1)
  private state = new ReplaySubject<State>(1)
  private history = new ReplaySubject<Array<Record<string, Agent>>>(1)
  private plans = new ReplaySubject<Array<Array<Record<string, Agent>>>>(1)
  private plan = new ReplaySubject<number | undefined>(1)
  private selectedLine = new ReplaySubject<string>(1)
  private stations = new ReplaySubject<StationsResponse>(1)
  private historyBuffer: Array<Record<string, Agent>> = []
  private interval?: number
  private currentTrajectoryId: string | null = null
  private stepQueue: string[] = []
  private isProcessingQueue = false

  public get playing() {
    return this.interval !== undefined
  }

  constructor(
    private dataService: DataService,
    private controllerService: ControllerService,
  ) {
    this.history.next([])
    this.plans.next([])
    this.stations.next({ city_cells: {}, outer_connection_points_per_city: {}, inter_city_lines: [] })
    this.selectedLine.next("0")
    Promise.all([
      this.dataService.getEnvs(),
      this.dataService.getPolicies(),
    ]).then(([envs, policies]) => {
      const defaultEnv = envs[0]?.id
      const defaultPolicy = policies[0]?.id
      if (defaultEnv && defaultPolicy) {
        this.reset(defaultEnv, defaultPolicy)
      }
    })
  }

  public getTrajectoryId(): string | null {
    return this.currentTrajectoryId
  }

  public getTransitions() {
    return this.transitions.asObservable()
  }

  public getAgents() {
    return this.agents.asObservable()
  }

  public getState() {
    return this.state.asObservable()
  }

  public getHistory(): Observable<Array<Record<string, Agent>>> {
    return this.history.asObservable()
  }

  public getPlans(): Observable<Array<Array<Record<string, Agent>>>> {
    return this.plans.asObservable()
  }

  public getPlan(): Observable<number | undefined> {
    return this.plan.asObservable()
  }

  public getStations(): Observable<StationsResponse> {
    return this.stations.asObservable()
  }

  public getSelectedLine(): Observable<string> {
    return this.selectedLine.asObservable()
  }

  public setSelectedLine(line: string) {
    this.selectedLine.next(line)
  }

  public next(policy?: string): void {
    if (!this.currentTrajectoryId || this.stepQueue.length >= 5) return
    this.stepQueue.push(this.currentTrajectoryId)
    this._drainQueue()
  }

  private _drainQueue(): void {
    if (this.isProcessingQueue || this.stepQueue.length === 0) return
    const trajectoryId = this.stepQueue.shift()!
    this.isProcessingQueue = true
    this.controllerService.stepTrajectory(trajectoryId)
      .then((trajectoryStep) => {
        const state: State = { steps: trajectoryStep.elapsed_steps, done: { __all__: trajectoryStep.done } }
        return this.dataService.getTrajectoryAgents(trajectoryId).then((agents) => {
          this.agents.next(agents)
          this.state.next(state)
          const snapshot = agents.reduce(
            (rec, agent) => { rec[String(agent.handle)] = agent; return rec },
            {} as Record<string, Agent>,
          )
          this.historyBuffer.push(snapshot)
          this.history.next([...this.historyBuffer])
          return state
        })
      })
      .then((state) => {
        this.isProcessingQueue = false
        if (state.done.__all__) {
          this.stepQueue = []
          this.stop()
        } else {
          this._drainQueue()
        }
      })
      .catch(() => {
        this.isProcessingQueue = false
        this.stepQueue = []
      })
  }

  public reset(environment?: string, policy?: string) {
    if (!environment || !policy) {
      return
    }
    this.stop()
    this.historyBuffer = []
    this.history.next([])
    this.controllerService.createTrajectory(environment, policy).then((trajectoryId) => {
      this.currentTrajectoryId = trajectoryId
      this.dataService.getTrajectoryTransitions(trajectoryId).then((transitions) => {
        this.dataService.getTrajectoryAgents(trajectoryId).then((agents) => {
          this.agents.next(agents)
          this.transitions.next(transitions)
        })
      })
      this.dataService.getTrajectoryStations(trajectoryId).then((stations) => {
        this.stations.next(stations)
      })
      this.state.next({ steps: 0, done: { __all__: false } })
    })
  }

  public play(policy?: string): void {
    this.interval = window.setInterval(() => {
      this.next(policy)
    }, 100)
  }

  public stop(): void {
    this.stepQueue = []
    if (this.interval) {
      clearInterval(this.interval)
      this.interval = undefined
    }
  }
}
