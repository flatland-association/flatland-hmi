import { HttpClient } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom, Subject } from 'rxjs'

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
  private resetEvent = new Subject<void>()

  constructor(private http: HttpClient) {
    this.resetEnv()
  }

  public stepEnv(policyIndex: number = 0) {
    return firstValueFrom(this.http.post<number>(`${BACKEND_URL}/step?plan_index=${policyIndex}`, {}))
  }

  public resetEnv() {
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/reset`, {})).then((state) => {
      this.resetEvent.next()
      return state
    })
  }

  public observeReset() {
    return this.resetEvent.asObservable()
  }
}
