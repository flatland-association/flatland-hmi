import { Injectable } from '@angular/core'
import {Observable, Subject} from 'rxjs'
import {DataService, TrajectoryStep} from './data.service'

export interface State {
  steps: number
  done: {
    __all__: boolean
    [key: string]: boolean
  }
}

@Injectable({
  providedIn: 'root',
})
export class ControllerService {
  private resetSubject = new Subject<void>()

  constructor(private dataService: DataService) {
  }

  public observeReset(): Observable<void> {
    return this.resetSubject.asObservable()
  }

  public createTrajectory(envId: string, policyId: string): Promise<string> {
    return this.dataService.createTrajectory(envId, policyId).then((trajectoryId) => {
      this.resetSubject.next()
      return trajectoryId
    })
  }

  public stepTrajectory(trajectoryId: string): Promise<TrajectoryStep> {
    return this.dataService.stepTrajectory(trajectoryId)
  }
}
