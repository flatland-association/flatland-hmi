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
  }

  public init(trajectoryId$: Observable<string | null>): void {
    // TODO cleanup
    const nonNull = trajectoryId$.pipe(filter((id): id is string => id !== null))
    nonNull.pipe(
      switchMap(id => from(this.dataService.getTrajectoryLines(id)))
    ).subscribe(lines => this.lines.next(lines))
    combineLatest([nonNull, this.selectedLine]).pipe(
      switchMap(([id, line]) => from(this.dataService.getTrajectoryLineTransitions(id, line)))
    ).subscribe(t => this.lineTransitions.next(t))
  }

  public loadTrajectory(transitions: Transitions, agents: Array<Agent>, stations: StationsResponse): void {
    this.state.next({steps: 0, done: {__all__: false}})
    this.selectedLine.next('0')
    this.agents.next(agents)
    this.transitions.next(transitions)
    this.stations.next(stations)
  }

  public clearHistory(): void {
    this.historyBuffer = []
    this.history.next([])
  }

  public applyStep(trajectoryStep: TrajectoryStep, agents: Array<Agent>): State {
    const state: State = {steps: trajectoryStep.elapsed_steps, done: {__all__: trajectoryStep.done}}
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
}
