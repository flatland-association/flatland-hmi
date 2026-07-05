import {HttpClient, HttpErrorResponse} from '@angular/common/http'
import {Injectable} from '@angular/core'
import {catchError, firstValueFrom, Observable, throwError} from 'rxjs'
import {ErrorMessageService} from './features/error-message/error-message.service'

const BACKEND_URL = 'http://localhost:8000'

export type Transitions = Array<Array<number>>

export interface LinkMap {
  grid: Transitions
  mapping: Array<[[number, number], [number, number]]>
  levels: Array<[[number, number], number]>
  incompleteCells: Array<[[number, number], string]>
}

export interface Env {
  id: string
  description: string
}

export interface PolicyOption {
  id: string
  description: string
}

export interface StationsResponse {
  stationEdges: Record<string, [number, number][]>
  stationGates: Record<string, Record<string, { name: string; pins: Record<string, { name: string; node: [number, number] }> }>>
  stationStoppingPoints: Record<string, Array<{ node: [number, number]; trackName: string }>>
}

export interface Link {
  cityFrom: string
  cityTo: string
  fromGate: string
  toGate: string
  label: string
  startStationName: string
  endStationName: string
}

export interface Agent {
  handle: number
  position: [number, number] | null
  direction: number
  moving: boolean
  target: [number, number]
  malfunction: number
}

export interface TrajectoryStep {
  ep_id: string
  policy_id: string
  env_id: string
  elapsed_steps: number
  done: boolean
}

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

export class DataService {
  /**
   * Encapsulates backend calls and their data types, implements centralized error handling.
   */
  constructor(private http: HttpClient, private errorMessageService: ErrorMessageService) {
  }

  private fetch<T>(obs: Observable<T>): Promise<T> {
    return firstValueFrom(
      obs.pipe(
        catchError((err: HttpErrorResponse) => {
          this.errorMessageService.errorMessage.set({
            title: `HTTP Error ${err.status}`,
            message: err.message,
          })
          return throwError(() => err)
        }),
      ),
    )
  }

  public getTrajectoryTransitions(trajectoryId: string) {
    return this.fetch(
      this.http.get<Transitions>(`${BACKEND_URL}/trajectories/${trajectoryId}/transitions`),
    )
  }

  public getTrajectoryLinkMap(trajectoryId: string, linkId: string) {
    return this.fetch(
      this.http.get<LinkMap>(`${BACKEND_URL}/trajectories/${trajectoryId}/link/${linkId}/map`),
    )
  }

  public getTrajectoryLinks(trajectoryId: string) {
    return this.fetch(
      this.http.get<Array<Link>>(`${BACKEND_URL}/trajectories/${trajectoryId}/links`),
    )
  }

  public getTrajectoryStations(trajectoryId: string) {
    return this.fetch(
      this.http.get<StationsResponse>(`${BACKEND_URL}/trajectories/${trajectoryId}/stations`),
    )
  }

  public getTrajectoryAgents(trajectoryId: string) {
    return this.fetch(
      this.http.get<Array<Agent>>(`${BACKEND_URL}/trajectories/${trajectoryId}/agents`),
    )
  }

  public getEnvs() {
    return this.fetch(this.http.get<Array<Env>>(`${BACKEND_URL}/envs`))
  }

  public getPolicies() {
    return this.fetch(this.http.get<Array<PolicyOption>>(`${BACKEND_URL}/policies`))
  }

  public createTrajectory(envId: string, policyId: string): Promise<string> {
    return this.fetch(
      this.http.post<string>(`${BACKEND_URL}/trajectories`, {env_id: envId, policy_id: policyId}),
    )
  }

  public stepTrajectory(trajectoryId: string): Promise<TrajectoryStep> {
    return this.fetch(
      this.http.post<TrajectoryStep>(`${BACKEND_URL}/trajectories/${trajectoryId}/step`, {}),
    )
  }
}
