import {Injectable} from '@angular/core'
import {filter, Observable, ReplaySubject, Subject} from 'rxjs'
import {DataService, State} from './data.service'
import {StateService} from './state.service'

@Injectable({
  providedIn: 'root',
})
/**
 * Entry points for user interactions: call data service and update state.
 * Also manages ticker while playing.
 */
export class ControllerService {
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
    this.stateService.init(this.trajectoryId.asObservable())
    this.trajectoryId
      .pipe(filter((id): id is string => id !== null))
      .subscribe(id => {
        this.currentTrajectoryId = id
      })
    Promise.all([dataService.getEnvs(), dataService.getPolicies()]).then(([envs, policies]) => {
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
      this.stateService.loadTrajectory(trajectoryId)
      this.resetSubject.next()
    })
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
        this.dataService.getTrajectoryAgents(trajectoryId)
          .then(agents => this.stateService.applyStep(trajectoryStep, agents))
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
