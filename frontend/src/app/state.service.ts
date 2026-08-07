import {Injectable} from '@angular/core'
import {Agent, Env, Link, PolicyOption, State, StationsResponse, TrajectoryStep, Transitions, LinkMap} from './data.service'
import {combineLatest, map, Observable, ReplaySubject} from 'rxjs'

@Injectable({
  providedIn: 'root',
})

export class StateService {
  /**
   * Holds shared data from backend for subscription by other components.
   */
  private transitions = new ReplaySubject<Transitions>(1)
  private agents = new ReplaySubject<Array<Agent>>(1)
  private state = new ReplaySubject<State>(1)
  private history = new ReplaySubject<Array<Record<string, Agent>>>(1)
  private plans = new ReplaySubject<Array<Array<Record<string, Agent>>>>(1)
  private plan = new ReplaySubject<number | undefined>(1)
  private selectedLink = new ReplaySubject<string>(1)
  private stations = new ReplaySubject<StationsResponse>(1)
  private links = new ReplaySubject<Array<Link>>(1)
  private linkMap = new ReplaySubject<LinkMap>(1)
  private envs = new ReplaySubject<Array<Env>>(1)
  private policies = new ReplaySubject<Array<PolicyOption>>(1)
  /** Time-machine replay position: number of elapsed steps to replay up to, matching `state.steps`; null means live/NOW. */
  private replayTime = new ReplaySubject<number | null>(1)
  private historyBuffer: Array<Record<string, Agent>> = []

  constructor() {
    this.history.next([])
    this.plans.next([])
    this.stations.next({
      stationEdges: {},
      stationGates: {},
      stationStoppingPoints: {},
    })
    this.selectedLink.next('0')
    this.replayTime.next(null)
  }

  public setEnvs(envs: Array<Env>): void {
    this.envs.next(envs)
  }

  public setPolicies(policies: Array<PolicyOption>): void {
    this.policies.next(policies)
  }

  public setLinks(lines: Array<Link>): void {
    this.links.next(lines)
  }

  public setLinkMap(t: LinkMap): void {
    this.linkMap.next(t)
  }

  public loadTrajectory(transitions: Transitions, agents: Array<Agent>, stations: StationsResponse): void {
    this.state.next({steps: 0, done: {__all__: false}})
    this.selectedLink.next('0')
    this.agents.next(agents)
    this.transitions.next(transitions)
    this.stations.next(stations)
  }

  public clearHistory(): void {
    this.historyBuffer = []
    this.history.next([])
    this.plans.next([])
    this.replayTime.next(null)
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

  /** Live agents when not replaying; otherwise the historical snapshot at the replay time. */
  public getDisplayedAgents(): Observable<Array<Agent>> {
    return combineLatest([this.agents, this.history, this.replayTime]).pipe(
      map(([liveAgents, history, replayTime]) => {
        if (replayTime === null) return liveAgents
        const snapshot = history[replayTime - 1]
        return snapshot ? Object.values(snapshot) : liveAgents
      }),
    )
  }

  public getReplayTime(): Observable<number | null> {
    return this.replayTime.asObservable()
  }

  public setReplayTime(t: number | null): void {
    this.replayTime.next(t)
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

  public setPlans(plans: Array<Array<Record<string, Agent>>>): void {
    this.plans.next(plans)
  }

  public getPlan(): Observable<number | undefined> {
    return this.plan.asObservable()
  }

  public getStations(): Observable<StationsResponse> {
    return this.stations.asObservable()
  }

  public getSelectedLink(): Observable<string> {
    return this.selectedLink.asObservable()
  }

  public getLinks(): Observable<Array<Link>> {
    return this.links.asObservable()
  }

  public getLinkMap(): Observable<LinkMap> {
    return this.linkMap.asObservable()
  }

  public getEnvs(): Observable<Array<Env>> {
    return this.envs.asObservable()
  }

  public getPolicies(): Observable<Array<PolicyOption>> {
    return this.policies.asObservable()
  }

  public selectLink(line: string) {
    this.selectedLink.next(line)
  }
}
