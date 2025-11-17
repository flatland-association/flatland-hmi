import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { firstValueFrom } from 'rxjs'
import { State } from '../controller.service'
import { Agent } from '../data.service'
import {MatCheckboxModule} from '@angular/material/checkbox';
import {FormsModule} from '@angular/forms';
import {MatInputModule} from '@angular/material/input';
import {MatSelectModule} from '@angular/material/select';
import {MatFormFieldModule} from '@angular/material/form-field';

// https://v19.material.angular.dev/components/select/overview
interface Food {
  value: string;
  viewValue: string;
}

@Component({
  selector: 'app-map',
  imports: [MatFormFieldModule, MatInputModule, MatSelectModule, FormsModule],
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

  foods: Food[] = [
     {value: 'steak-0', viewValue: 'Steak'},
     {value: 'pizza-1', viewValue: 'Pizza'},
     {value: 'tacos-2', viewValue: 'Tacos'},
   ];

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

  public onChangeFood(p:string){
    console.log(p)
    this.stateService.reset()
   }
}
