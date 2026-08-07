import {Injectable} from '@angular/core'
import {filter, from, Observable, ReplaySubject, Subject, switchMap} from 'rxjs'
import {DataService, State} from './data.service'
import {StateService} from './state.service'

@Injectable({
  providedIn: 'root',
})

export class ControllerService {
  /**
   * Entry points for user interactions: call data service and update state.
   * Also manages ticker while playing.
   */
  private trajectoryId = new ReplaySubject<string | null>(1)
  private resetSubject = new Subject<void>()
  private currentTrajectoryId: string | null = null
  private stepQueue: string[] = []
  private isProcessingQueue = false
  private interval?: number

  public get playing(): boolean {
    return this.interval !== undefined
  }

  constructor(private dataService: DataService, private stateService: StateService) {
    const nonNull = this.trajectoryId.pipe(filter((id): id is string => id !== null))

    nonNull.subscribe(id => {
      this.currentTrajectoryId = id
    })

    nonNull.pipe(
      switchMap(id => from(dataService.getTrajectoryLinks(id)))
    ).subscribe(lines => stateService.setLinks(lines))

    Promise.all([dataService.getEnvs(), dataService.getPolicies()]).then(([envs, policies]) => {
      stateService.setEnvs(envs)
      stateService.setPolicies(policies)
      const defaultEnv = envs[0]?.id
      const defaultPolicy = policies[0]?.id
      if (defaultEnv && defaultPolicy) {
        this.reset(defaultEnv, defaultPolicy)
      }
    })
  }

  public observeReset(): Observable<void> {
    return this.resetSubject.asObservable()
  }

  public reset(environment?: string, policy?: string): void {
    if (!environment || !policy) return
    this.stop()
    this.stateService.clearHistory()
    this.dataService.createTrajectory(environment, policy).then(trajectoryId => {
      this.trajectoryId.next(trajectoryId)
      this.selectLink('0')
      this.resetSubject.next()
      Promise.all([
        this.dataService.getTrajectoryTransitions(trajectoryId),
        this.dataService.getTrajectoryAgents(trajectoryId),
        this.dataService.getTrajectoryStations(trajectoryId),
        this.dataService.getTrajectoryAgentPlans(trajectoryId),
      ]).then(([transitions, agents, stations, plans]) => {
        this.stateService.loadTrajectory(transitions, agents, stations)
        this.stateService.setPlans(plans)
      })
    })
  }

  public selectLink(line: string): void {
    this.stateService.selectLink(line)
    if (!this.currentTrajectoryId) return
    this.dataService.getTrajectoryLinkMap(this.currentTrajectoryId, line)
      .then(t => this.stateService.setLinkMap(t))
  }

  public step(): void {
    this.stop()
    this.next()
  }

  public next(): void {
    if (!this.currentTrajectoryId || this.stepQueue.length >= 5) return
    this.stepQueue.push(this.currentTrajectoryId)
    this._drainQueue()
  }

  private _drainQueue(): void {
    if (this.isProcessingQueue || this.stepQueue.length === 0) return
    const trajectoryId = this.stepQueue.shift()!
    this.isProcessingQueue = true
    this.dataService.stepTrajectory(trajectoryId)
      .then(trajectoryStep =>
        Promise.all([
          this.dataService.getTrajectoryAgents(trajectoryId),
          this.dataService.getTrajectoryAgentPlans(trajectoryId),
        ]).then(([agents, plans]) => {
          // Apply the step (and its history/timestep update) before publishing plans, so Marey's
          // plans subscriber sees the up-to-date timestep and aligns plans to the new "now".
          const state = this.stateService.applyStep(trajectoryStep, agents)
          this.stateService.setPlans(plans)
          return state
        })
      )
      .then(state => {
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

  public play(): void {
    this.interval = window.setInterval(() => this.next(), 100)
  }

  public stop(): void {
    this.stepQueue = []
    if (this.interval) {
      clearInterval(this.interval)
      this.interval = undefined
    }
  }
}
