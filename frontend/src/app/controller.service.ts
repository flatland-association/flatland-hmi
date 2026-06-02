import { HttpClient, HttpParams } from '@angular/common/http'
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

@Injectable({
  providedIn: 'root',
})
export class ControllerService {
  private resetSubject = new Subject<void>()

  constructor(private http: HttpClient) {}

  public observeReset(): Observable<void> {
    return this.resetSubject.asObservable()
  }

  public stepEnv(policy?: string) {
    let params = new HttpParams()
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/step`, {}, {params}))
  }

  public resetEnv(environment?: string, policy?: string) {
    let params = new HttpParams()
    if (environment) {
      params = params.append('environment', environment)
    }
    if (policy) {
        params = params.append('policy', policy)
    }
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/reset`, {}, { params })).then((state) => {
      this.resetSubject.next()
      return state
    })
  }
}
