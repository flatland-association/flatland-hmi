import {Injectable} from '@angular/core'
import {Agent, DataService, LineOption, State, StationsResponse, TrajectoryStep, Transitions, ZwlResponse} from './data.service'
import {combineLatest, filter, from, Observable, ReplaySubject, switchMap} from 'rxjs'

@Injectable({
  providedIn: 'root',
})
/**
 * Holds shared data from backend for subscription by other components.
 */
export class StateService {
  private transitions = new ReplaySubject<Transitions>(1)
  private agents = new ReplaySubject<Array<Agent>>(1)
  private state = new ReplaySubject<State>(1)
  private history = new ReplaySubject<Array<Record<string, Agent>>>(1)
  private plans = new ReplaySubject<Array<Array<Record<string, Agent>>>>(1)
  private plan = new ReplaySubject<number | undefined>(1)
  private selectedLine = new ReplaySubject<string>(1)
  private stations = new ReplaySubject<StationsResponse>(1)
  private lines = new ReplaySubject<Array<LineOption>>(1)
  private lineTransitions = new ReplaySubject<ZwlResponse>(1)
  private historyBuffer: Array<Record<string, Agent>> = []
  private trajectoryId = new ReplaySubject<string | null>(1)

  constructor(private dataService: DataService) {
    this.history.next([])
    this.plans.next([])
    this.stations.next({
      city_cells: {},
      outer_connection_points_per_city: {},
      inter_city_lines: [],
      train_stations: {},
      train_station_labels: {},
      outer_connection_point_labels: {},
    })
    this.selectedLine.next('0')
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

    const nonNullTrajectoryId = this.trajectoryId.pipe(filter((id): id is string => id !== null))

    nonNullTrajectoryId.pipe(
      switchMap(trajectoryId => from(this.dataService.getTrajectoryLines(trajectoryId)))
    ).subscribe(lines => this.lines.next(lines))

    combineLatest([nonNullTrajectoryId, this.selectedLine]).pipe(
      switchMap(([trajectoryId, selectedLine]) =>
        from(this.dataService.getTrajectoryLineTransitions(trajectoryId, selectedLine))
      )
    ).subscribe(transitions => this.lineTransitions.next(transitions))
  }

  public getTrajectoryId() {
    return this.trajectoryId.asObservable()
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

  public getLines(): Observable<Array<LineOption>> {
    return this.lines.asObservable()
  }

  public getLineTransitions(): Observable<ZwlResponse> {
    return this.lineTransitions.asObservable()
  }

  public selectLine(line: string) {
    this.selectedLine.next(line)
  }

  public applyStep(trajectoryId: string, trajectoryStep: TrajectoryStep): Promise<State> {
    const state: State = {steps: trajectoryStep.elapsed_steps, done: {__all__: trajectoryStep.done}}
    return this.dataService.getTrajectoryAgents(trajectoryId).then((agents) => {
      this.agents.next(agents)
      this.state.next(state)
      const snapshot = agents.reduce(
        (rec, agent) => {
          rec[String(agent.handle)] = agent;
          return rec
        },
        {} as Record<string, Agent>,
      )
      this.historyBuffer.push(snapshot)
      this.history.next([...this.historyBuffer])
      return state
    })
  }

  public reset(environment?: string, policy?: string) {
    if (!environment || !policy) return
    this.historyBuffer = []
    this.history.next([])
    this.dataService.createTrajectory(environment, policy).then((trajectoryId) => {
      this.trajectoryId.next(trajectoryId)
      this.dataService.getTrajectoryTransitions(trajectoryId).then((transitions) => {
        this.dataService.getTrajectoryAgents(trajectoryId).then((agents) => {
          this.agents.next(agents)
          this.transitions.next(transitions)
        })
      })
      this.dataService.getTrajectoryStations(trajectoryId).then((stations) => {
        this.stations.next(stations)
      })
      this.state.next({steps: 0, done: {__all__: false}})
      this.selectedLine.next('0')
    })
  }
}
