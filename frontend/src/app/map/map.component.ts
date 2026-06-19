import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import {combineLatest} from 'rxjs'
import {Agent, State} from '../data.service'
import {ControllerService} from '../controller.service'
import {FormsModule} from '@angular/forms';

interface SelectOption {
  value: string
  label: string
}

@Component({
  selector: 'app-map',
  imports: [FormsModule],
  templateUrl: './map.component.html',
  styleUrl: './map.component.scss',
})
export class MapComponent implements OnInit {
  public mapClasses: Array<Array<MapCell>> = []
  public agents: Array<Agent> = []
  public state: State = {
    steps: 0,
    done: {
      __all__: false,
    },
  }

  public policyOptions: SelectOption[] = []
  public currentPolicy = ''

  public envOptions: SelectOption[] = []
  public currentEnv = ''


  constructor(
    public stateService: StateService,
    public controllerService: ControllerService,
    public rendererService: RendererService,
  ) {}

  ngOnInit() {
    this.stateService.getEnvs().subscribe(envs => {
      this.envOptions = envs.map(e => ({ value: e.id, label: e.description }))
      this.currentEnv = this.envOptions[0]?.value ?? ''
    })
    this.stateService.getPolicies().subscribe(policies => {
      this.policyOptions = policies.map(p => ({ value: p.id, label: p.description }))
      this.currentPolicy = this.policyOptions[0]?.value ?? ''
    })
    this.stateService.getState().subscribe((state) => (this.state = state))
    combineLatest([
      this.stateService.getTransitions(),
      this.stateService.getAgents(),
      this.stateService.getStations(),
    ]).subscribe(([transitions, agents, stations]) => {
      this.mapClasses = this.rendererService.renderMap(transitions, agents, stations)
    })
    this.stateService.getAgents().subscribe((agents) => (this.agents = agents))
  }

  public getSteps() {
    return this.state?.steps ?? 0
  }


}
