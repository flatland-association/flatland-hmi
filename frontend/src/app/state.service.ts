import { Injectable } from '@angular/core'
import { Agent, DataService, Transitions } from './data.service'
import { Observable, ReplaySubject } from 'rxjs'
import { ControllerService, State } from './controller.service'

@Injectable({
  providedIn: 'root',
})
export class StateService {
  private transitions = new ReplaySubject<Transitions>(1)
  private agents = new ReplaySubject<Array<Agent>>(1)
  private state = new ReplaySubject<State>(1)
  private history = new ReplaySubject<Array<Record<string, Agent>>>(1)
  private plans = new ReplaySubject<Array<Array<Record<string, Agent>>>>(1)
  private plan = new ReplaySubject<number | undefined>(1)
  private historyBuffer: Array<Record<string, Agent>> = []
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
    this.history.next([])
    this.plans.next([])
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

  public getHistory(): Observable<Array<Record<string, Agent>>> {
    return this.history.asObservable()
  }

  public getPlans(): Observable<Array<Array<Record<string, Agent>>>> {
    return this.plans.asObservable()
  }

  public getPlan(): Observable<number | undefined> {
    return this.plan.asObservable()
  }

  public next(policy?: string) {
    return this.controllerService.stepEnv(policy).then((state) => {
      this.dataService.getAgents().then((agents) => {
        this.agents.next(agents)
        this.state.next(state)
        const snapshot = agents.reduce(
          (rec, agent) => { rec[String(agent.handle)] = agent; return rec },
          {} as Record<string, Agent>,
        )
        this.historyBuffer.push(snapshot)
        this.history.next([...this.historyBuffer])
      })
      return state
    })
  }

  public reset(environment?: string, policy?: string) {
    this.stop()
    this.historyBuffer = []
    this.history.next([])
    this.controllerService.resetEnv(environment, policy).then((state) => {
      this.dataService.getTransitions().then((transitions) => {
        this.dataService.getAgents().then((agents) => {
          this.agents.next(agents)
          this.transitions.next(transitions)
        })
      })
      this.state.next(state)
    })
  }

  public play(policy?: string) {
    this.interval = window.setInterval(() => {
      this.next(policy).then(({ done }) => {
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
