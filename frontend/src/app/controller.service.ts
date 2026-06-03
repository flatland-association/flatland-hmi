import { HttpClient } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom, Observable, Subject } from 'rxjs'

const BACKEND_URL = 'http://localhost:8000'

export interface State {
  steps: number
  done: {
    __all__: boolean
    [key: string]: boolean
  }
}

export interface TrajectoryStep {
  ep_id: string
  policy_id: string
  env_id: string
  elapsed_steps: number
  done: boolean
}

@Injectable({
  providedIn: 'root',
})
export class ControllerService {
  private resetSubject = new Subject<void>()

  constructor(private http: HttpClient) {}

  public observeReset(): Observable<void> {
    return this.resetSubject.asObservable()
  }

  public createTrajectory(envId: string, policyId: string): Promise<string> {
    return firstValueFrom(
      this.http.post<string>(`${BACKEND_URL}/trajectories`, { env_id: envId, policy_id: policyId }),
    ).then((trajectoryId) => {
      this.resetSubject.next()
      return trajectoryId
    })
  }

  public stepTrajectory(trajectoryId: string): Promise<TrajectoryStep> {
    return firstValueFrom(
      this.http.post<TrajectoryStep>(`${BACKEND_URL}/trajectories/${trajectoryId}/step`, {}),
    )
  }
}
