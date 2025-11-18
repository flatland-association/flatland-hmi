import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { firstValueFrom } from 'rxjs'
import { State } from '../controller.service'
import { Agent } from '../data.service'
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

  public policyOptions: SelectOption[] = [
    {value: 'policy-0', label: 'Random Policy'},
    {value: 'policy-1', label: 'Deadlock Avoidance Heuristic'},
  ]
  public currentPolicy = this.policyOptions[0].value

  public envOptions: SelectOption[] = [
    {value: 'generated-0', label: 'Generated environment 30 x 30, 7 agents'},
    {value: 'generated-1', label: 'Generated environment 50 x 50, 7 agents'}
  ]
  public currentEnv = this.envOptions[0].value

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
  ) {}

  ngOnInit() {
    this.stateService.getState().subscribe((state) => (this.state = state))
    this.stateService.getTransitions().subscribe((transitions) =>
      firstValueFrom(this.stateService.getAgents()).then((agents) => {
        this.mapClasses = this.rendererService.renderMap(transitions, agents)
      }),
    )
    this.stateService.getAgents().subscribe((agents) => (this.agents = agents))
  }

  public getSteps() {
    return this.state?.steps ?? 0
  }


}
