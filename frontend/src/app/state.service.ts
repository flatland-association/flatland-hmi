import { Injectable } from '@angular/core'
import { Agent, DataService, Transitions } from './data.service'
import { ReplaySubject, Subject } from 'rxjs'
import { ControllerService, State } from './controller.service'

@Injectable({
  providedIn: 'root',
})
export class StateService {
  private transitions = new ReplaySubject<Transitions>(1)
  private agents = new ReplaySubject<Array<Agent>>(1)
  private state = new ReplaySubject<State>(1)
  private interval?: number

  public get playing() {
    return this.interval !== undefined
  }

  constructor(
    private dataService: DataService,
    private controllerService: ControllerService,
  ) {
    this.dataService.getTransitions().then((transitions) => {
      this.transitions.next(transitions)
    })
    this.dataService.getAgents().then((agents) => {
      this.agents.next(agents)
    })
  }

  public getTransitions() {
    return this.transitions.asObservable()
  }

  public getAgents() {
    return this.agents.asObservable()
  }

  public getState() {
    return this.state.asObservable()
  }

  public next() {
    return this.controllerService.stepEnv().then((state) => {
      this.dataService.getAgents().then((agents) => {
        this.agents.next(agents)
        this.state.next(state)
      })
      return state
    })
  }

  public reset() {
    this.stop()
    this.controllerService.resetEnv().then((state) => {
      this.dataService.getTransitions().then((transitions) => {
        this.dataService.getAgents().then((agents) => {
          this.agents.next(agents)
          this.transitions.next(transitions)
        })
      })
      this.state.next(state)
    })
  }

  public play() {
    this.interval = window.setInterval(() => {
      this.next().then(({ done }) => {
        if (done.__all__) {
          this.stop()
        }
      })
    }, 100)
  }

  public stop() {
    if (this.interval) {
      clearInterval(this.interval)
      this.interval = undefined
    }
  }
}
