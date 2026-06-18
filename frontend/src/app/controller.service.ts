import {Injectable} from '@angular/core'
import {filter, Observable, Subject} from 'rxjs'
import {DataService, State} from './data.service'
import {StateService} from './state.service'

@Injectable({
  providedIn: 'root',
})
export class ControllerService {
  private resetSubject = new Subject<void>()
  private currentTrajectoryId: string | null = null
  private stepQueue: string[] = []
  private isProcessingQueue = false
  private interval?: number

  public get playing(): boolean {
    return this.interval !== undefined
  }

  constructor(private dataService: DataService, private stateService: StateService) {
    this.stateService.getTrajectoryId()
      .pipe(filter((id): id is string => id !== null))
      .subscribe((id) => {
        this.currentTrajectoryId = id
        this.stop()
      })
  }

  public _next(): void {
    if (!this.currentTrajectoryId || this.stepQueue.length >= 5) return
    this.stepQueue.push(this.currentTrajectoryId)
    this._drainQueue()
  }

  private _drainQueue(): void {
    if (this.isProcessingQueue || this.stepQueue.length === 0) return
    const trajectoryId = this.stepQueue.shift()!
    this.isProcessingQueue = true
    this.dataService.stepTrajectory(trajectoryId)
      .then((trajectoryStep) => this.stateService.applyStep(trajectoryId, trajectoryStep))
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

  public play(): void {
    this.interval = window.setInterval(() => this._next(), 100)
  }

  public stop(): void {
    this.stepQueue = []
    if (this.interval) {
      clearInterval(this.interval)
      this.interval = undefined
    }
  }
}
