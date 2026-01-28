import { HttpClient, HttpParams } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom } from 'rxjs'

const BACKEND_URL = 'http://localhost:8000'

export interface State {
  steps: number
  done: {
    __all__: boolean
    [key: string]: boolean
  },
  max_steps: number
}

@Injectable({
  providedIn: 'root',
})
export class ControllerService {
  constructor(private http: HttpClient) {}

  public stepEnv(policy?: string, env_time?: number) {
    let params = new HttpParams()
    if (env_time){
      params = params.append('env_time', env_time)
    }
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/step/`, {}, {params}))
  }

  public resetEnv(environment?: string, policy?: string) {
    let params = new HttpParams()
    if (environment) {
      params = params.append('environment', environment)
    }
    if (policy) {
        params = params.append('policy', policy)
    }
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/reset`, {}, {params}))
  }
}
