# Deadline Unreal Engine Service plugin
To use this plugin copy the `UnrealDeadlineService` and the `MoviePipelineDeadline` to the `Plugins` directory located in your Unreal Project's directory.

For further documentation on this plugin, please refer to the [Unreal Engine 5](https://docs.thinkboxsoftware.com/products/deadline/10.3/1_User%20Manual/manual/app-index.html#u) documentation available on our doc website.
> **_Note:_** 
> This plugin's web service mode has a dependency on `urllib3` that is not packaged with this 
> plugin. To resolve this, execute the `requirements.txt` file in the 
> `unreal/UnrealDeadlineService/Content/Python/Lib` directory and save the `urllib3` 
> site packages in the `Win64` directory of the above path. 
> The engine will automatically add this library to the Python path and make it 
> available to the Python interpreter.

# Unreal Movie Pipeline Deadline plugin

Although usage documentation for this plugin is a work in progress, 
it does not limit the use of other Deadline service features. 
This plugin serves as an example of how to use the aforementioned Deadline services.

> **_Note:_** 
> Currently, it is recommended to build the Engine from source as the current 
> state of the plugins do not have compiled versions for the released Editor binaries. 
> Building the Engine from source allows you to install the necessary dependencies 
> for compiling the Engine plugins locally. This issue will be remedied in future releases. Follow 
> the instructions on [Downloading Unreal Engine Source Code](https://docs.unrealengine.com/5.1/en-US/downloading-unreal-engine-source-code/) 
> to download the Engine versions from source and build the Engine locally.

# Local Testing

To test the functionality of the plugins, use the [Meerkat Demo](https://www.unrealengine.com/marketplace/en-US/product/meerkat-demo-02)
from the marketplace. This project is a self-contained cinematic project that 
allows you to test movie rendering with the latest version of the Engine binaries. 
This is the project we use for internal testing of the plugins.

> **_Note:_** 
> When you enable the plugins for this project, the Engine may need to 
> recompile the custom Editor for this project.
