import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { firstValueFrom } from 'rxjs'
import { State } from '../controller.service'
import { Agent } from '../data.service'
import { FormsModule } from '@angular/forms';
import { MatSliderModule } from '@angular/material/slider';

interface SelectOption {
  value: string
  label: string
}

@Component({
  selector: 'app-map',
  imports: [FormsModule,MatSliderModule],
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
    max_steps: 0,
  }

  public policyOptions: SelectOption[] = [
    {value: 'policy-0', label: 'Random Policy'},
    {value: 'policy-1', label: 'Deadlock Avoidance Heuristic'},
  ]
  public currentPolicy = this.policyOptions[0].value
  public currentStep = 0

  public envOptions: SelectOption[] = [
    {value: 'generated-0', label: 'Generated environment 30 x 30, 7 agents'},
    {value: 'generated-1', label: 'Generated environment 50 x 50, 10 agents'},
    {value: 'scenario_1', label: 'Scenario 1'},
  ]
  public currentEnv = this.envOptions[0].value

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
  ) {}

  ngOnInit() {
    this.stateService.getState().subscribe((state) => {
      this.state = state
    })
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
