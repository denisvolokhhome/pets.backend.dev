<?php

namespace App\Services;


use Illuminate\Support\Facades\Storage;

class FileService{

    public function uploadImage($request)
    {


        if(!$request->hasFile('image')) {
            return response()->json(['upload_file_not_found'], 400);
        }

        if($request->file('image')->getSize()/1000 > env('IMG_MAX_FILE_SIZE')){
            return response()->json(['uploaded file size is ' . $request->file('image')->getSize()/1000 . 'KB, which is bigger then allowed: '.  env('IMG_MAX_FILE_SIZE') . 'Kb and was not uploaded'], 400);
        }

        $allowedfileExtension=['jpg','png'];
        $file = $request->file('image');
        $errors = [];

        $extension = $file->getClientOriginalExtension();
        $check = in_array($extension,$allowedfileExtension);

        if($check) {

            //save the file to local storage
            Storage::putFile(env('IMG_PHYSICAL_FILE_PATH'), $request->image);

            // generate pretty file name path
            $path = env('IMG_VIRTUAL_FILE_PATH').$request->image->hashName();

            return response()->json([
                'path' => $path,
                'fileName' => $request->image->getClientOriginalName(),
                'image successfully uploaded' ,

            ], 200);


        } else {
            return response()->json(['invalid_file_format, only this will work: png, jpg'], 422);
        }


    }

}
